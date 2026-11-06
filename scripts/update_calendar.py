"""Refresh data/events.json from the public NMA Google Calendar."""

import json
import re
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

FEED = "https://calendar.google.com/calendar/ical/nmatorah26%40gmail.com/public/full.ics"
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "events.json"


def unfold(text):
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r"\n[ \t]", "", text)


def unescape(value):
    return (
        value.replace("\\n", "\n")
        .replace("\\N", "\n")
        .replace("\\,", ",")
        .replace("\\;", ";")
        .replace("\\\\", "\\")
        .strip()
    )


def parse_when(raw, params):
    if raw.endswith("Z"):
        return datetime.strptime(raw, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    if len(raw) == 8:
        return datetime.strptime(raw, "%Y%m%d").replace(tzinfo=timezone.utc)
    return datetime.strptime(raw, "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)


def field(body, name):
    match = re.search(r"^" + name + r"(?:;[^:\n]*)?:(.*)$", body, re.M)
    return unescape(match.group(1)) if match else ""


def sponsorship_notes(description):
    shiur = ""
    meals = []
    for line in description.splitlines():
        text = line.strip().rstrip(".")
        low = text.lower()
        if low.startswith("meal sponsored by"):
            meals.append(text)
        elif low.startswith("sponsored by") and not shiur:
            shiur = text
    return shiur, meals


def attachment(body):
    match = re.search(r"^ATTACH((?:;[^:\n]*)?):(.*)$", body, re.M)
    if not match:
        return "", ""
    params, url = match.group(1), unescape(match.group(2))
    filename = ""
    named = re.search(r"FILENAME=([^;]+)", params)
    if named:
        filename = named.group(1).strip().strip('"')
    file_id = ""
    found = re.search(r"[?&]id=([A-Za-z0-9_-]+)", url)
    if found:
        file_id = found.group(1)
    return filename, file_id


def events_from_ics(text):
    now = datetime.now(timezone.utc)
    window_end = now + timedelta(days=70)
    found = []
    for block in unfold(text).split("BEGIN:VEVENT")[1:]:
        body = block.split("END:VEVENT", 1)[0]
        start_match = re.search(r"^DTSTART(?:;([^:\n]*))?:(.*)$", body, re.M)
        end_match = re.search(r"^DTEND(?:;([^:\n]*))?:(.*)$", body, re.M)
        if not start_match:
            continue
        start = parse_when(start_match.group(2).strip(), start_match.group(1) or "")
        end = parse_when(end_match.group(2).strip(), end_match.group(1) or "") if end_match else start
        if end < now - timedelta(days=120) or start > window_end:
            continue
        summary = field(body, "SUMMARY")
        if not summary or summary.lower() == "busy":
            continue
        filename, file_id = attachment(body)
        shiur, meals = sponsorship_notes(field(body, "DESCRIPTION"))
        found.append(
            {
                "summary": summary,
                "start": start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "end": end.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "location": field(body, "LOCATION"),
                "filename": filename,
                "fileId": file_id,
                "sponsor": shiur,
                "meals": meals,
            }
        )
    found.sort(key=lambda item: item["start"])
    return found


def main():
    request = urllib.request.Request(FEED, headers={"User-Agent": "NMA-Website"})
    with urllib.request.urlopen(request, timeout=30) as response:
        text = response.read().decode("utf-8")
    payload = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "events": events_from_ics(text),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
