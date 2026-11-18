#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build fgo_jp.ics from Mooncell (fgo.wiki) Semantic MediaWiki data.

Run:  python fetch_fgo.py [--months 6] [--out fgo_jp.ics]
"""

import argparse
import datetime
import hashlib
import json
import os
import sys
import urllib.parse
import urllib.request

API = "https://fgo.wiki/api.php"
FIELDS = "|?EventNameJP|?EventStartJP|?EventEndJP|?EventType|?EventExlinkJP"
UA = "game-calendar/1.0 (https://github.com/yomubi/game-calendar)"


def ask(query, timeout=60):
    url = API + "?action=ask&format=json&query=" + urllib.parse.quote(query)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", "replace")
    data = json.loads(raw)
    if "query" not in data or "results" not in data.get("query", {}):
        raise RuntimeError("unexpected SMW response: " + raw[:400])
    return data["query"]["results"]


def pick_time(printouts, field):
    vals = printouts.get(field) or []
    if not vals:
        return None
    v = vals[0]
    if isinstance(v, dict):
        ts = v.get("timestamp")
        if ts is not None:
            try:
                return datetime.datetime.fromtimestamp(
                    int(ts), datetime.timezone.utc
                )
            except (ValueError, OSError):
                return None
        raw = v.get("raw")
        if raw:
            parts = str(raw).split("/")
            if len(parts) >= 6:
                try:
                    y, mo, d, hh, mm = (int(x) for x in parts[1:6])
                    jst = datetime.datetime(
                        y, mo, d, hh, mm, tzinfo=datetime.timezone(
                            datetime.timedelta(hours=9))
                    )
                    return jst.astimezone(datetime.timezone.utc)
                except ValueError:
                    return None
    return None


def pick_text(printouts, field):
    vals = printouts.get(field) or []
    if not vals:
        return ""
    v = vals[0]
    if isinstance(v, dict):
        return str(v.get("fulltext") or v.get("raw") or "").strip()
    return str(v).strip()


def esc(text):
    return (
        str(text)
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def fold(line):
    """RFC5545 line folding: keep each physical line <= 74 octets."""
    out = []
    cur = ""
    for ch in line:
        if len((cur + ch).encode("utf-8")) > 74:
            out.append(cur)
            cur = " " + ch
        else:
            cur += ch
    out.append(cur)
    return out


def fmt(dt):
    return dt.strftime("%Y%m%dT%H%M%SZ")


def build(months_back, out_path):
    since = (datetime.date.today()
             - datetime.timedelta(days=months_back * 31)).isoformat()
    query = "[[EventStartJP::>=" + since + "]]" + FIELDS
    results = ask(query)

    events = []
    for key, item in results.items():
        printouts = item.get("printouts") or {}
        start = pick_time(printouts, "EventStartJP")
        end = pick_time(printouts, "EventEndJP")
        if not start:
            continue
        if not end:
            end = start + datetime.timedelta(hours=1)
        news = pick_text(printouts, "EventExlinkJP")
        etype = pick_text(printouts, "EventType") or "Event"
        title = key.strip()

        uid = "fgo-" + hashlib.sha1(
            (title + start.isoformat()).encode("utf-8")
        ).hexdigest()[:10] + "@lumia.local"

        desc = "Type: " + etype
        if news:
            desc += "\nNews: " + news
        desc += "\nSrc: fgo.wiki Mooncell"

        events.append({
            "uid": uid,
            "start": start,
            "end": end,
            "summary": "FGO | " + title,
            "desc": desc,
        })

    events.sort(key=lambda e: e["start"], reverse=True)

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Lumia//FGO JP Event Calendar//CN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:FGO JP Events",
        "X-WR-TIMEZONE:Asia/Tokyo",
    ]
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for e in events:
        lines += [
            "BEGIN:VEVENT",
            "UID:" + e["uid"],
            "DTSTAMP:" + stamp,
            "DTSTART:" + fmt(e["start"]),
            "DTEND:" + fmt(e["end"]),
            "SUMMARY:" + esc(e["summary"]),
            "DESCRIPTION:" + esc(e["desc"]),
            "CATEGORIES:FGO",
            "TRANSP:TRANSPARENT",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")

    physical = []
    for line in lines:
        physical.extend(fold(line))

    with open(out_path, "w", encoding="utf-8", newline="\r\n") as fh:
        fh.write("\n".join(physical) + "\n")

    print("Wrote %d events -> %s" % (len(events), out_path))
    return len(events)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", type=int, default=6)
    ap.add_argument("--out", default="fgo_jp.ics")
    args = ap.parse_args()
    n = build(args.months, args.out)
    if n == 0:
        sys.exit("no events found, aborting")


if __name__ == "__main__":
    main()
