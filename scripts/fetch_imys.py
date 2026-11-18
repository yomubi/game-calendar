#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""あいりすミスティリア！ 官方站「最新情報」-> ics

两种取数方式：
  --source rss   （默认）https://dmm-imys.com/news/feed/  WordPress RSS
                 一页 10 条，item 里的 content:encoded 直接带整篇正文，
                 所以「開催期間：11月18日 12:00 ～ 11月29日 12:59」不用再进详情页。
                 分页用 ?paged=N。
  --source html  列表页 /news/ 逐条抓详情（老路子，RSS 挂了时备用）。

RSS 的 item 没有分类字段，分类从标题关键词推断：
  召喚 -> 召喚 / イベント -> イベント / 不具合 -> 不具合 / 其余 -> ニュース

用法：
    python fetch_imys.py --pages 2 --out aimis_jp.ics
    python fetch_imys.py --source html --pages 3 --out aimis_jp.ics
"""
import argparse
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from hashlib import sha1

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
JST = timezone(timedelta(hours=9))
BASE = "https://dmm-imys.com"
FEED = BASE + "/news/feed/"
CONTENT_NS = "{http://purl.org/rss/1.0/modules/content/}encoded"

WANT = {"イベント", "召喚"}

# 标题里『』包着的就是活动/卡池本名，拿它当去重键
NAME = re.compile(r'『([^』」]+)』?')


def core(title):
    m = NAME.search(title)
    t = m.group(1) if m else title
    t = re.sub(r'【[^】]{1,8}】', '', t)
    t = re.sub(r'(期間限定|ステップアップ|イベント|召喚|開催|のお知らせ|キャンペーン)', '', t)
    t = re.sub(r'[\s　]+', '', t)
    t = re.sub(r'[!！。、]+$', '', t)
    return t or title

TITLE_KW = ["開催", "開始", "開幕", "実装", "追加", "予告", "復刻", "終了", "配布",
            "更新", "登場", "実施"]
DETAIL_CATS = {"イベント", "召喚"}

ART = re.compile(
    r'<article class="entry">.*?'
    r'<h1><a href="(?P<link>[^"]+)">(?P<title>[^<]+)</a></h1>.*?'
    r'<span class="category[^"]*">(?P<cat>[^<]+)</span>.*?'
    r'<time class="date_r">(?P<date>[\d.]+)</time>',
    re.S)

# 開催期間：11月18日 12:00 ～ 11月29日 12:59
# 也吃「11月18日(火) 12:00 ～ 11月29日(日) 12:59」「11/18 12:00～11/29 12:59」
DAY = r'(?:\d{1,2})月(?:\d{1,2})日(?:\([^)]{1,4}\))?\s*(?:\d{1,2}):(?:\d{2})'
PERIOD = re.compile(
    r'(\d{1,2})月(\d{1,2})日(?:\([^)]{1,4}\))?\s*(\d{1,2}):(\d{2})\s*'
    r'(?:より|から)?\s*[～〜~\-–—]\s*'
    r'(?:(\d{1,2})月)?(\d{1,2})日(?:\([^)]{1,4}\))?\s*(\d{1,2}):(\d{2})')


def get(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
                   "image/avif,image/webp,*/*;q=0.8"),
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        "Accept-Encoding": "identity",
        "Referer": "https://dmm-imys.com/",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Cache-Control": "no-cache",
    })
    with urllib.request.urlopen(req, timeout=45) as r:
        return r.read().decode("utf-8", "replace")


def strip_tags(html):
    t = re.sub(r'(?s)<script.*?</script>|<style.*?</style>', ' ', html)
    t = re.sub(r'<[^>]+>', ' ', t)
    t = re.sub(r'&nbsp;', ' ', t)
    return re.sub(r'\s+', ' ', t)


def guess_cat(title):
    if "不具合" in title or "障害" in title:
        return "不具合"
    if "召喚" in title or "ガチャ" in title:
        return "召喚"
    if "イベント" in title:
        return "イベント"
    return "ニュース"


# ---------------------------------------------------------------- RSS 取数

def rss_collect(pages):
    rows, seen, ok = [], set(), 0
    for n in range(1, pages + 1):
        url = FEED if n == 1 else "%s?paged=%d" % (FEED, n)
        try:
            raw = get(url)
            ok += 1
        except Exception as e:
            print("feed page %d failed: %s" % (n, e), file=sys.stderr)
            continue
        raw = raw.lstrip("\ufeff \r\n\t")
        i = raw.find("<rss")
        if i > 0:
            raw = raw[i:]
        try:
            root = ET.fromstring(raw)
        except ET.ParseError as e:
            print("feed page %d parse error: %s" % (n, e), file=sys.stderr)
            continue
        items = root.findall("./channel/item")
        print("feed page %d: %d items" % (n, len(items)), file=sys.stderr)
        for it in items:
            link = (it.findtext("link") or "").strip()
            title = re.sub(r'\s+', ' ', it.findtext("title") or "").strip()
            if not link or link in seen:
                continue
            seen.add(link)
            try:
                pub = parsedate_to_datetime(it.findtext("pubDate")).astimezone(JST)
            except Exception:
                continue
            body = strip_tags(it.find(CONTENT_NS).text or "") if it.find(CONTENT_NS) is not None else ""
            rows.append({
                "link": link,
                "title": title,
                "cat": guess_cat(title),
                "date": pub.strftime("%Y.%m.%d"),
                "body": body,
            })
    if ok == 0:
        print("ALL feed pages failed - site unreachable, refusing to overwrite",
              file=sys.stderr)
        sys.exit(3)
    if not rows:
        print("no items parsed - feed may have changed, refusing to overwrite",
              file=sys.stderr)
        sys.exit(4)
    return rows


# --------------------------------------------------------------- HTML 取数

def page_url(n):
    return BASE + "/news/" if n <= 1 else "%s/news/0/page/%d/" % (BASE, n)


def html_collect(pages):
    rows, seen, ok = [], set(), 0
    for n in range(1, pages + 1):
        try:
            html = get(page_url(n))
            ok += 1
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
                "body": "",
            })
    if ok == 0:
        print("ALL pages failed - site unreachable, refusing to overwrite",
              file=sys.stderr)
        sys.exit(3)
    if not rows:
        print("no articles parsed - layout may have changed, refusing to overwrite",
              file=sys.stderr)
        sys.exit(4)
    return rows


# ------------------------------------------------------------------- 时间

def period_from_text(text, pub_date):
    m = PERIOD.search(text)
    if not m:
        return None
    sm, sd, sh, smi, em_, ed, eh, emi = m.groups()
    sm, sd, sh, smi = int(sm), int(sd), int(sh), int(smi)
    em = int(em_) if em_ else sm
    ed, eh, emi = int(ed), int(eh), int(emi)
    sy = ey = pub_date.year
    if sm < pub_date.month - 6:          # 「1月」写在 12 月的公告里 -> 明年
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


def find_period(row, pub_date):
    """优先用 RSS 正文，没有再进详情页。"""
    if row.get("body"):
        span = period_from_text(row["body"], pub_date)
        if span:
            return span
    try:
        html = get(row["link"])
    except Exception as e:
        print("  detail failed %s: %s" % (row["link"], e), file=sys.stderr)
        return None
    return period_from_text(strip_tags(html), pub_date)


# -------------------------------------------------------------------- ics

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
    ap.add_argument("--source", choices=["rss", "html"], default="rss")
    ap.add_argument("--pages", type=int, default=2)
    ap.add_argument("--out", default="aimis_jp.ics")
    ap.add_argument("--calname", default="あいミス（日服）— 活动")
    ap.add_argument("--keep-bugs", action="store_true")
    ap.add_argument("--keep-news", action="store_true",
                    help="连「ニュース」类也收进来（默认只收 イベント/召喚）")
    ap.add_argument("--no-dedup", action="store_true",
                    help="同一活动在予告/正式/复刻公告里各留一条（默认合并）")
    ap.add_argument("--no-detail", action="store_true",
                    help="不抓详情页（无正文的条目退化为全天事件）")
    ap.add_argument("--grace", type=int, default=7,
                    help="已结束的事件再保留几天（默认 7）")
    a = ap.parse_args()

    rows = rss_collect(a.pages) if a.source == "rss" else html_collect(a.pages)

    want = set(WANT)
    if a.keep_news:
        want.add("ニュース")

    picked = []
    for r in rows:
        if not a.keep_bugs and r["cat"] == "不具合":
            continue
        if r["cat"] not in want:
            continue
        if not any(k in r["title"] for k in TITLE_KW):
            continue
        try:
            d = datetime.strptime(r["date"], "%Y.%m.%d")
        except ValueError:
            continue
        picked.append((d, r))
    picked.sort(key=lambda x: x[0])

    today = datetime.now(JST).date()
    cutoff = today - timedelta(days=a.grace)

    # 同一活动会被发多次（予告 / 開催 / 复刻），按『本名』合并：
    # 优先留「イベント」而不是「召喚」，其次留拿到精确期间的。
    chosen = {}
    for d, r in picked:
        span = None
        if not a.no_detail and r["cat"] in DETAIL_CATS:
            span = find_period(r, d)
        end_day = span[1].date() if span else (d + timedelta(days=1)).date()
        if end_day < cutoff:
            continue
        key = r["link"] if a.no_dedup else core(r["title"])
        rank = (1 if r["cat"] == "イベント" else 0, 1 if span else 0)
        prev = chosen.get(key)
        if prev is None or rank > prev[0]:
            chosen[key] = (rank, d, r, span)

    items = sorted(chosen.values(), key=lambda x: (x[1], x[2]["title"]))

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//lumia//imys-feed//CN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:" + esc(a.calname),
        "X-WR-TIMEZONE:Asia/Tokyo",
    ]

    exact = 0
    for _rank, d, r, span in items:
        uid = sha1(r["link"].encode("utf-8")).hexdigest()[:10] + "@lumia.local"
        summary = "あいミス | [" + r["cat"] + "] " + r["title"]
        ev = ["BEGIN:VEVENT", "UID:" + uid,
              "DTSTAMP:" + d.strftime("%Y%m%dT000000Z")]
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

    print("source=%s total=%d picked=%d events=%d exact=%d -> %s"
          % (a.source, len(rows), len(picked), len(items), exact, a.out),
          file=sys.stderr)


if __name__ == "__main__":
    main()
