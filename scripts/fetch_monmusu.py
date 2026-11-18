#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""モンスター娘TD 攻略 Wiki 首页的「開催中イベント」区块 -> ics

源：https://monmusu-td.wikiru.jp/
区块形如：
    開催中イベント
    ・行楽遊覧-孤島浄化譚-
      11/16 ～ 12/03(木) メンテ迄
    復刻イベント
    ・邪妖調伏戦「鵺」
    ・邪妖調伏戦「白蛇」
    ・妖怪のヒミツ
      11/16 ～ 12/03 メンテ迄
    イベント履歴 / キャンペーン履歴

用法： python fetch_monmusu.py --out monmusu_jp.ics
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
URL = "https://monmusu-td.wikiru.jp/"

RANGE = re.compile(r'(\d{1,2})/(\d{1,2})\s*[～〜~]\s*(\d{1,2})/(\d{1,2})')


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


def _dates(m):
    y = datetime.now(JST).year
    sm, sd, em, ed = (int(x) for x in m.groups())
    sy, ey = y, y
    if sm < datetime.now(JST).month - 6:
        sy += 1
    if em < sm:
        ey = sy + 1
    try:
        s = datetime(sy, sm, sd, tzinfo=JST).date()
        e = datetime(ey, em, ed, tzinfo=JST).date()
    except ValueError:
        return None
    return s, e


def parse_block(html):
    """返回 [(分组名, [条目名...], (开始, 结束))]，日期为 date。

    标签先换成空格压成一行连续文本，再按「開催中イベント / 復刻イベント」
    切段——因为日期区间会被 <br> 切断成 `11/16 ～ |12/03(木)`，
    逐行匹配必定漏掉主活动那一组。
    """
    plain = re.sub(r'<[^>]+>', ' ', html).replace('&nbsp;', ' ')
    plain = re.sub(r'\s+', ' ', plain)

    i = plain.find('開催中イベント')
    if i < 0:
        return []
    j = plain.find('イベント履歴', i)
    if j < 0:
        j = i + 2000
    body = plain[i:j]

    k = body.find('復刻イベント')
    if k > 0:
        segs = [('開催中', body[:k]), ('復刻', body[k:])]
    else:
        segs = [('開催中', body)]

    out = []
    for grp, seg in segs:
        seg = seg.replace('開催中イベント', ' ').replace('復刻イベント', ' ').strip()
        m = RANGE.search(seg)
        if not m:
            continue
        de = _dates(m)
        if not de:
            continue
        rest = (seg[:m.start()] + ' ' + seg[m.end():])
        rest = rest.replace('メンテ迄', ' ').replace('メンテまで', ' ')
        names = []
        for x in rest.split('・'):
            x = re.sub(r'[\s　]*[\(（][^\)）]*[\)）]\s*$', '', x).strip()
            x = re.sub(r'\s+', '', x) if '「' not in x else re.sub(r'\s{2,}', ' ', x).strip()
            if x:
                names.append(x)
        if names:
            out.append((grp, names, de))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="monmusu_jp.ics")
    ap.add_argument("--calname", default="モンスター娘TD（日服）— 活动")
    ap.add_argument("--grace", type=int, default=3)
    a = ap.parse_args()

    try:
        html = get(URL)
    except Exception as e:
        print("fetch failed: %s" % e, file=sys.stderr)
        sys.exit(3)

    groups = parse_block(html)
    if not groups:
        print("no event block parsed - layout changed?", file=sys.stderr)
        sys.exit(4)

    today = datetime.now(JST).date()
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//lumia//monmusu-feed//CN",
        "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
        "X-WR-CALNAME:" + esc(a.calname),
        "X-WR-TIMEZONE:Asia/Tokyo",
    ]
    n = 0
    for grp, names, (s, e) in groups:
        if e < today - timedelta(days=a.grace):
            continue
        prefix = "復刻 " if grp == "復刻" else ""
        for name in names:
            title = "モンスター娘TD | " + prefix + name
            uid = sha1((name + str(s)).encode("utf-8")).hexdigest()[:10] + "@lumia.local"
            lines += [
                "BEGIN:VEVENT", "UID:" + uid,
                "DTSTAMP:" + s.strftime("%Y%m%dT000000Z"),
                "DTSTART;VALUE=DATE:" + s.strftime("%Y%m%d"),
                "DTEND;VALUE=DATE:" + (e + timedelta(days=1)).strftime("%Y%m%d"),
                "SUMMARY:" + esc(title),
                "DESCRIPTION:" + esc(URL + "  （%s ～ %s メンテ迄）" % (s, e)),
                "TRANSP:TRANSPARENT", "END:VEVENT",
            ]
            n += 1
    lines.append("END:VCALENDAR")

    body = "\r\n".join(fold(l) for l in lines) + "\r\n"
    with open(a.out, "w", encoding="utf-8", newline="") as f:
        f.write(body)
    print("groups=%d events=%d -> %s" % (len(groups), n, a.out), file=sys.stderr)
    for grp, names, (s, e) in groups:
        print("  [%s] %s  %s ～ %s" % (grp, " / ".join(names), s, e),
              file=sys.stderr)


if __name__ == "__main__":
    main()
