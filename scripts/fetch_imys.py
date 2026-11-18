#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""あいりすミスティリア！ 官方站「最新情報」-> ics

站点：https://dmm-imys.com/news/  （WordPress，列表静态渲染）
列表每条 = <article class="entry"> 里
    <h1><a href>标题</a></h1>
    <span class="category cat_xxx">分类</span>
    <time class="date_r">2026.11.18</time>
详情页正文里有「開催期間：11月18日 12:00 ～ 11月29日 12:59」这种起止，
能抽到就生成精确事件，抽不到退回全天事件（日期=公告日）。

用法：
    python fetch_imys.py --pages 2 --out aimis_jp.ics
    python fetch_imys.py --pages 3 --no-detail   # 只列表、不抓详情
"""
import argparse
import re
import sys
import urllib.request
from datetime import datetime, timezone, timedelta
from hashlib import sha1

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
JST = timezone(timedelta(hours=9))
BASE = "https://dmm-imys.com"

WANT = {"イベント", "召喚", "ニュース"}
TITLE_KW = ["開催", "開始", "開幕", "実装", "追加", "予告", "復刻", "終了", "配布"]
DETAIL_CATS = {"イベント", "召喚"}

ART = re.compile(
    r'<article class="entry">.*?'
    r'<h1><a href="(?P<link>[^"]+)">(?P<title>[^<]+)</a></h1>.*?'
    r'<span class="category[^"]*">(?P<cat>[^<]+)</span>.*?'
    r'<time class="date_r">(?P<date>[\d.]+)</time>',
    re.S)

# 開催期間：11月18日 12:00 ～ 11月29日 12:59
PERIOD = re.compile(
    r'(\d{1,2})月(\d{1,2})日\s*(\d{1,2}):(\d{2})\s*[～〜~\-–—]\s*'
    r'(\d{1,2})月(\d{1,2})日\s*(\d{1,2}):(\d{2})')


def get(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        "Accept-Language": "ja,en;q=0.8",
    })
    with urllib.request.urlopen(req, timeout=45) as r:
        return r.read().decode("utf-8", "replace")


def strip_tags(html):
    t = re.sub(r'(?s)<script.*?</script>|<style.*?</style>', ' ', html)
    t = re.sub(r'<[^>]+>', ' ', t)
    t = re.sub(r'&nbsp;', ' ', t)
    return re.sub(r'\s+', ' ', t)


def page_url(n):
    return BASE + "/news/" if n <= 1 else "%s/news/0/page/%d/" % (BASE, n)


def collect(pages):
    rows, seen = [], set()
    for n in range(1, pages + 1):
        try:
            html = get(page_url(n))
        except Exception as e:
            print("page %d failed: %s" % (n, e), file=sys.stderr)
            continue
        hits = list(ART.finditer(html))
        print("page %d: %d articles" % (n, len(hits)), file=sys.stderr)
        for m in hits:
            link = m.group("link")
            if link in seen:
                continue
            seen.add(link)
            rows.append({
                "link": link,
                "title": re.sub(r'\s+', ' ', m.group("title")).strip(),
                "cat": m.group("cat").strip(),
                "date": m.group("date").strip(),
            })
    return rows


def find_period(link, pub_date):
    """抓详情页，返回 (start_dt, end_dt) 或 None。时间按 JST。"""
    try:
        html = get(link)
    except Exception as e:
        print("  detail failed %s: %s" % (link, e), file=sys.stderr)
        return None
    text = strip_tags(html)
    m = PERIOD.search(text)
    if not m:
        return None
    sm, sd, sh, smi, em, ed, eh, emi = (int(x) for x in m.groups())
    sy, ey = pub_date.year, pub_date.year
    if sm < pub_date.month - 6:      # 「1月」写在 12 月的公告里 -> 明年
        sy += 1
    if (em, ed) < (sm, sd) or em < sm:
        ey = sy + 1
    try:
        start = datetime(sy, sm, sd, sh, smi, tzinfo=JST)
        end = datetime(ey, em, ed, eh, emi, tzinfo=JST)
    except ValueError:
        return None
    if end <= start:
        return None
    return start, end


def esc(s):
    return (s.replace("\\", "\\\\")
             .replace(";", "\\;")
             .replace(",", "\\,")
             .replace("\n", "\\n"))


def fold(line, limit=74):
    out, cur, cur_b = [], "", 0
    for ch in line:
        b = len(ch.encode("utf-8"))
        if cur_b + b > limit:
            out.append(cur)
            cur, cur_b = " " + ch, 1 + b
        else:
            cur += ch
            cur_b += b
    out.append(cur)
    return "\r\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=2)
    ap.add_argument("--out", default="aimis_jp.ics")
    ap.add_argument("--calname", default="あいミス（日服）— 活动")
    ap.add_argument("--keep-bugs", action="store_true")
    ap.add_argument("--no-detail", action="store_true",
                    help="不抓详情页（全部退化为全天事件）")
    ap.add_argument("--grace", type=int, default=7,
                    help="已结束的事件再保留几天（默认 7）")
    a = ap.parse_args()

    rows = collect(a.pages)

    picked = []
    for r in rows:
        if not a.keep_bugs and r["cat"] not in WANT:
            continue
        if not any(k in r["title"] for k in TITLE_KW):
            continue
        try:
            d = datetime.strptime(r["date"], "%Y.%m.%d")
        except ValueError:
            continue
        picked.append((d, r))
    picked.sort(key=lambda x: x[0])

    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//lumia//imys-feed//CN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:" + esc(a.calname),
        "X-WR-TIMEZONE:Asia/Tokyo",
    ]

    today = datetime.now(JST).date()
    cutoff = today - timedelta(days=a.grace)

    exact = 0
    for d, r in picked:
        span = None
        if not a.no_detail and r["cat"] in DETAIL_CATS:
            span = find_period(r["link"], d)
        end_day = span[1].date() if span else (d + timedelta(days=1)).date()
        if end_day < cutoff:
            continue          # 早就结束了，别塞进日历
        uid = sha1(r["link"].encode("utf-8")).hexdigest()[:10] + "@lumia.local"
        summary = "あいミス | [" + r["cat"] + "] " + r["title"]
        ev = ["BEGIN:VEVENT", "UID:" + uid, "DTSTAMP:" + now]
        if span:
            exact += 1
            s, e = span
            ev += [
                "DTSTART:" + s.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
                "DTEND:" + e.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
            ]
        else:
            ev += [
                "DTSTART;VALUE=DATE:" + d.strftime("%Y%m%d"),
                "DTEND;VALUE=DATE:" + (d + timedelta(days=1)).strftime("%Y%m%d"),
            ]
        ev += [
            "SUMMARY:" + esc(summary),
            "DESCRIPTION:" + esc(r["link"]),
            "URL:" + r["link"],
            "TRANSP:TRANSPARENT",
            "END:VEVENT",
        ]
        lines += ev
    lines.append("END:VCALENDAR")

    body = "\r\n".join(fold(l) for l in lines) + "\r\n"
    with open(a.out, "w", encoding="utf-8", newline="") as f:
        f.write(body)

    print("total=%d kept=%d exact=%d -> %s"
          % (len(rows), len(picked), exact, a.out), file=sys.stderr)


if __name__ == "__main__":
    main()
