#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""御城プロジェクト:RE 攻略 Wiki 首页「アップデート」区块 -> ics

源：https://scre.swiki.jp/
区块形如：
    <p><a href="..." title="武神双覇！毛利元就＆石田三成 (22h)">武神双覇！毛利元就＆石田三成</a>
       <span class="wikicolor" style="color:Red">武神</span><br />
       <span class="wikicolor" style="color:Green"><strong>期間：11月17日~12月3日</strong></span></p>

用法： python fetch_oshiro.py --out oshiro_jp.ics
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
URL = "https://scre.swiki.jp/"

ITEM = re.compile(
    r'<a href="[^"]*" title="([^"]+?) \([^)]*\)">[^<]*</a>\s*'
    r'<span class="wikicolor"[^>]*>([^<]*)</span>\s*<br\s*/?>\s*'
    r'<span class="wikicolor"[^>]*><strong>期間：(\d{1,2})月(\d{1,2})日'
    r'\s*[~～〜]\s*(\d{1,2})月(\d{1,2})日</strong></span>',
    re.S)


def get(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        "Accept-Language": "ja,en;q=0.8",
    })
    with urllib.request.urlopen(req, timeout=45) as r:
        return r.read().decode("utf-8", "replace")


def esc(s):
    return (s.replace("\\", "\\\\").replace(";", "\\;")
             .replace(",", "\\,").replace("\n", "\\n"))


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


def parse(html):
    out = []
    now = datetime.now(JST)
    for m in ITEM.finditer(html):
        name, kind = m.group(1).strip(), m.group(2).strip()
        sm, sd, em, ed = (int(x) for x in m.groups()[2:])
        sy = now.year
        if sm < now.month - 6:
            sy += 1
        ey = sy + 1 if em < sm else sy
        try:
            s = datetime(sy, sm, sd, tzinfo=JST).date()
            e = datetime(ey, em, ed, tzinfo=JST).date()
        except ValueError:
            continue
        out.append((name, kind, s, e))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="oshiro_jp.ics")
    ap.add_argument("--calname", default="御城プロジェクト:RE（日服）— 活动")
    ap.add_argument("--grace", type=int, default=3)
    a = ap.parse_args()

    try:
        html = get(URL)
    except Exception as e:
        print("fetch failed: %s" % e, file=sys.stderr)
        sys.exit(3)

    items = parse(html)
    if not items:
        print("no update block parsed - layout changed?", file=sys.stderr)
        sys.exit(4)

    today = datetime.now(JST).date()
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//lumia//oshiro-feed//CN",
        "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
        "X-WR-CALNAME:" + esc(a.calname),
        "X-WR-TIMEZONE:Asia/Tokyo",
    ]
    n = 0
    for name, kind, s, e in items:
        if e < today - timedelta(days=a.grace):
            continue
        tag = (" [%s]" % kind) if kind else ""
        title = "城プロRE | " + name + tag
        uid = sha1((name + str(s)).encode("utf-8")).hexdigest()[:10] + "@lumia.local"
        lines += [
            "BEGIN:VEVENT", "UID:" + uid,
            "DTSTAMP:" + s.strftime("%Y%m%dT000000Z"),
            "DTSTART;VALUE=DATE:" + s.strftime("%Y%m%d"),
            "DTEND;VALUE=DATE:" + (e + timedelta(days=1)).strftime("%Y%m%d"),
            "SUMMARY:" + esc(title),
            "DESCRIPTION:" + esc(URL + "  （%s ～ %s）" % (s, e)),
            "TRANSP:TRANSPARENT", "END:VEVENT",
        ]
        n += 1
    lines.append("END:VCALENDAR")

    body = "\r\n".join(fold(l) for l in lines) + "\r\n"
    with open(a.out, "w", encoding="utf-8", newline="") as f:
        f.write(body)
    print("events=%d -> %s" % (n, a.out), file=sys.stderr)
    for name, kind, s, e in items:
        print("  %s [%s]  %s ～ %s" % (name, kind, s, e), file=sys.stderr)


if __name__ == "__main__":
    main()
