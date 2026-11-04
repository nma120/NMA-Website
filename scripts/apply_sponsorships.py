"""Write a successful Tuesday sponsorship onto the NMA Google Calendar.

A gift for an evening that is not on the calendar yet becomes a private event,
with an email and a popup reminder one week before. An evening that already
exists keeps its current privacy. The first gift for a date is the one named.
"""

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

CALENDAR_ID = "nmatorah26@gmail.com"
TIMEZONE = ZoneInfo("America/New_York")
PLACE = "6447 Dieterle Crescent, Rego Park, NY 11374"
ENTRANCE = "The entrance is in the back, down the stairs."
WEEK_MINUTES = 7 * 24 * 60
MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


def request_json(url, method="GET", payload=None, headers=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("User-Agent", "Mozilla/5.0 (compatible; NMA-Website/1.0; +https://nmatorah.org)")
    req.add_header("Accept", "application/json")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")[:500].replace("\n", " ")
        raise RuntimeError("Request failed with HTTP " + str(error.code) + ": " + detail) from None


def google_token():
    body = urllib.parse.urlencode(
        {
            "client_id": os.environ["GOOGLE_CLIENT_ID"],
            "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
            "refresh_token": os.environ["GOOGLE_REFRESH_TOKEN"],
            "grant_type": "refresh_token",
        }
    ).encode("utf-8")
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=body)
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))["access_token"]


def pairs(value, found=None):
    found = [] if found is None else found
    if isinstance(value, dict):
        question = value.get("question") or value.get("label") or value.get("title") or value.get("key")
        answer = value.get("answer") or value.get("value") or value.get("response")
        if question and answer and not isinstance(answer, (dict, list)):
            found.append((str(question).strip(), str(answer).strip()))
        for child in value.values():
            pairs(child, found)
    elif isinstance(value, list):
        for child in value:
            pairs(child, found)
    return found


def parse_date(text):
    match = re.search(r"(20\d{2})-(\d{1,2})-(\d{1,2})", text)
    if match:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    match = re.search(r"(\d{1,2})/(\d{1,2})/(20\d{2})", text)
    if match:
        return date(int(match.group(3)), int(match.group(1)), int(match.group(2)))
    match = re.search(
        r"(january|february|march|april|may|june|july|august|september|october|november|december)"
        r"\s+(\d{1,2})(?:,|\s)+(20\d{2})",
        text,
        re.I,
    )
    if match:
        return date(int(match.group(3)), MONTHS[match.group(1).lower()], int(match.group(2)))
    match = re.search(
        r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june|july|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
        r"\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b",
        text,
        re.I,
    )
    if match:
        month_name = match.group(1).lower()[:3]
        month = 9 if month_name == "sep" else MONTHS[next(name for name in MONTHS if name.startswith(month_name))]
        return upcoming(month, int(match.group(2)))
    match = re.search(r"\b(\d{1,2})/(\d{1,2})\b", text)
    if match and int(match.group(1)) <= 12:
        return upcoming(int(match.group(1)), int(match.group(2)))
    return None


def upcoming(month, day):
    today = datetime.now(TIMEZONE).date()
    try:
        found = date(today.year, month, day)
    except ValueError:
        return None
    if found < today - timedelta(days=1):
        return date(today.year + 1, month, day)
    return found


def campaign_text(payment, titles):
    raw = payment.get("campaign") or payment.get("campaign_id") or payment.get("campaignId") or ""
    campaign_id = ""
    title = ""
    if isinstance(raw, dict):
        campaign_id = str(raw.get("id") or "")
        title = str(raw.get("title") or raw.get("name") or "")
    else:
        campaign_id = str(raw)
    if not title and campaign_id:
        title = titles.get(campaign_id, "")
    if not title:
        title = str(payment.get("campaign_title") or payment.get("campaign_name") or payment.get("form_name") or "")
    form = str(payment.get("form") or "")
    return campaign_id, title, form, (title + " " + form).lower()


def gift_kind(payment, titles):
    campaign_id, title, form, blob = campaign_text(payment, titles)
    wanted = os.environ.get("ZEFFY_CAMPAIGN_ID", "").strip()
    if wanted and wanted not in (campaign_id, title, form):
        return ""
    if "liquid" in blob or "alcohol" in blob:
        return "liquid"
    if "meal" in blob or "food" in blob:
        return "meal"
    if "tuesday" in blob or "shiur" in blob or "sponsor" in blob:
        return "shiur"
    return ""


def sponsorship_from(payment, titles):
    kind = gift_kind(payment, titles)
    if kind != "shiur" and kind != "meal":
        return None
    answers = pairs(payment)
    evening = None
    name = ""
    for question, answer in answers:
        found = parse_date(answer) or parse_date(question)
        if found and evening is None:
            evening = found
        label = question.lower()
        if re.search(r"name|sponsor|display", label) and not parse_date(answer):
            name = answer.strip(" .")
    contact = payment.get("buyer") if isinstance(payment.get("buyer"), dict) else {}
    if not contact and isinstance(payment.get("contact"), dict):
        contact = payment.get("contact")
    if not name:
        name = " ".join(
            part
            for part in (
                contact.get("first_name") or contact.get("firstName") or payment.get("buyer_first"),
                contact.get("last_name") or contact.get("lastName") or payment.get("buyer_last"),
            )
            if part
        ).strip()
        if not name:
            name = str(contact.get("name") or "").strip()
    if not name or evening is None:
        return None
    tribute = {}
    if isinstance(payment.get("tribute"), dict):
        tribute = payment.get("tribute")
    for item in payment.get("items") or []:
        if tribute:
            break
        if isinstance(item, dict) and isinstance(item.get("tribute"), dict):
            tribute = item.get("tribute")
    honored = str(tribute.get("honouree_name") or tribute.get("honoree_name") or tribute.get("name") or "").strip(" .")
    tribute_type = str(tribute.get("type") or tribute.get("kind") or "").lower()
    dedication = ""
    if honored:
        if honored.lower().startswith("in honor") or honored.lower().startswith("in memory"):
            dedication = " " + honored
        elif "memory" in tribute_type:
            dedication = " in memory of " + honored
        else:
            dedication = " in honor of " + honored
    if kind == "meal":
        line = "Meal sponsored by " + name + dedication
    else:
        line = "Sponsored by " + name + dedication
    created = str(payment.get("created") or payment.get("created_at") or payment.get("createdAt") or "")
    return {"date": evening, "kind": kind, "line": line, "paymentId": str(payment.get("id") or ""), "created": created}


def campaign_ok(payment, titles):
    return bool(gift_kind(payment, titles))


def paged(token, resource):
    found = []
    cursor = ""
    while True:
        query = urllib.parse.urlencode({"limit": "100", **({"starting_after": cursor} if cursor else {})})
        page = request_json(
            "https://api.zeffy.com/api/v1/" + resource + "?" + query,
            headers={"Authorization": "Bearer " + token},
        )
        batch = page.get("data") or page.get(resource) or page.get("results") or []
        if isinstance(page, list):
            batch = page
        found.extend(batch)
        cursor = str(page.get("next_cursor") or "") if isinstance(page, dict) else ""
        if not cursor or not page.get("has_more"):
            break
    return found


def campaign_titles(token):
    titles = {}
    for item in paged(token, "campaigns"):
        campaign_id = str(item.get("id") or "")
        title = str(item.get("title") or item.get("name") or "")
        if campaign_id and title:
            titles[campaign_id] = title
    return titles


def calendar_headers(token):
    return {"Authorization": "Bearer " + token, "Accept": "application/json"}


def events_on(token, evening):
    start = datetime(evening.year, evening.month, evening.day, 0, 0, tzinfo=TIMEZONE)
    end = start + timedelta(days=1)
    query = urllib.parse.urlencode(
        {
            "timeMin": start.isoformat(),
            "timeMax": end.isoformat(),
            "singleEvents": "true",
            "orderBy": "startTime",
            "maxResults": "20",
        }
    )
    calendar = urllib.parse.quote(CALENDAR_ID, safe="")
    listed = request_json(
        "https://www.googleapis.com/calendar/v3/calendars/" + calendar + "/events?" + query,
        headers=calendar_headers(token),
    )
    return listed.get("items") or []


def recorded_ids(item):
    private = ((item.get("extendedProperties") or {}).get("private") or {})
    raw = private.get("zeffyPaymentIds") or private.get("zeffyPaymentId") or ""
    return set(str(raw).split())


def line_kind(text):
    low = text.strip().lower()
    if low.startswith("meal sponsored by"):
        return "meal"
    if low.startswith("liquid asset sponsored by"):
        return "liquid"
    if low.startswith("sponsored by"):
        return "shiur"
    return ""


def already_recorded(items, gift):
    for item in items:
        if gift["paymentId"] and gift["paymentId"] in recorded_ids(item):
            return item
        description = item.get("description") or ""
        if gift["line"] and gift["line"] in description:
            return item
        if gift["kind"] != "meal":
            for note in description.splitlines():
                if line_kind(note) == gift["kind"]:
                    return item
    return None


def reminder():
    return {
        "useDefault": False,
        "overrides": [
            {"method": "email", "minutes": WEEK_MINUTES},
            {"method": "popup", "minutes": WEEK_MINUTES},
        ],
    }


def create_private_event(token, gift):
    start = datetime(gift["date"].year, gift["date"].month, gift["date"].day, 20, 0, tzinfo=TIMEZONE)
    end = start.replace(hour=22)
    event = {
        "summary": "NMA Torah Tuesday",
        "description": gift["line"] + ".\n" + ENTRANCE,
        "location": PLACE,
        "start": {"dateTime": start.isoformat(), "timeZone": "America/New_York"},
        "end": {"dateTime": end.isoformat(), "timeZone": "America/New_York"},
        "visibility": "private",
        "reminders": reminder(),
        "extendedProperties": {"private": {"zeffyPaymentIds": gift["paymentId"]}},
    }
    calendar = urllib.parse.quote(CALENDAR_ID, safe="")
    return request_json(
        "https://www.googleapis.com/calendar/v3/calendars/" + calendar + "/events",
        method="POST",
        payload=event,
        headers=calendar_headers(token),
    )


def add_sponsor_line(token, item, gift):
    description = item.get("description") or ""
    if gift["line"] not in description:
        description = (gift["line"] + ".\n" + description).strip()
    private = ((item.get("extendedProperties") or {}).get("private") or {})
    ids = recorded_ids(item)
    if gift["paymentId"]:
        ids.add(gift["paymentId"])
    private["zeffyPaymentIds"] = " ".join(sorted(ids))
    patch = {
        "description": description,
        "extendedProperties": {"private": private},
    }
    calendar = urllib.parse.quote(CALENDAR_ID, safe="")
    return request_json(
        "https://www.googleapis.com/calendar/v3/calendars/"
        + calendar
        + "/events/"
        + urllib.parse.quote(item["id"], safe=""),
        method="PATCH",
        payload=patch,
        headers=calendar_headers(token),
    )


def ends_at_eleven(item):
    raw = ((item.get("end") or {}).get("dateTime")) or ""
    if not raw:
        return False
    when = datetime.fromisoformat(raw)
    if when.tzinfo is None:
        when = when.replace(tzinfo=TIMEZONE)
    local = when.astimezone(TIMEZONE)
    return local.hour == 23 and local.minute == 0


def set_ten_pm(token, item):
    raw = item["end"]["dateTime"]
    when = datetime.fromisoformat(raw)
    if when.tzinfo is None:
        when = when.replace(tzinfo=TIMEZONE)
    local = when.astimezone(TIMEZONE).replace(hour=22, minute=0, second=0, microsecond=0)
    calendar = urllib.parse.quote(CALENDAR_ID, safe="")
    return request_json(
        "https://www.googleapis.com/calendar/v3/calendars/"
        + calendar
        + "/events/"
        + urllib.parse.quote(item["id"], safe=""),
        method="PATCH",
        payload={"end": {"dateTime": local.isoformat(), "timeZone": "America/New_York"}},
        headers=calendar_headers(token),
    )


def apply_gift(token, gift):
    existing = events_on(token, gift["date"])
    ours = [
        item
        for item in existing
        if "nma" in (item.get("summary") or "").lower() or "torah" in (item.get("summary") or "").lower()
    ]
    recorded = already_recorded(ours or existing, gift)
    if recorded:
        if (recorded.get("visibility") or "") == "private" and ends_at_eleven(recorded):
            set_ten_pm(token, recorded)
            print("Set the evening to 8:00–10:00 PM:", gift["date"].isoformat())
        else:
            print("Already recorded:", gift["date"].isoformat(), gift["line"])
        return
    if ours:
        add_sponsor_line(token, ours[0], gift)
        print("Updated:", gift["date"].isoformat(), gift["line"])
        return
    create_private_event(token, gift)
    print("Created a private evening:", gift["date"].isoformat(), gift["line"])


def main():
    zeffy = os.environ.get("ZEFFY_API_KEY", "").strip()
    google_ready = all(os.environ.get(name, "").strip() for name in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN"))
    if not zeffy or not google_ready:
        print("Sponsorship helper is waiting for the Zeffy key and Google calendar access.")
        return
    token = google_token()
    titles = campaign_titles(zeffy)
    found = paged(zeffy, "payments")
    print("Campaigns read:", len(titles))
    print("Payments read:", len(found))
    gifts = []
    for payment in found:
        status = str(payment.get("status") or "succeeded").lower()
        if status not in ("succeeded", "success", "paid", "completed"):
            continue
        if not campaign_ok(payment, titles):
            continue
        gift = sponsorship_from(payment, titles)
        if gift:
            gifts.append(gift)
        else:
            print("Skipped a completed sponsorship. The date or the name was missing.")
    gifts.sort(key=lambda item: (item["date"], item["kind"], item["created"], item["paymentId"]))
    seen = set()
    for gift in gifts:
        key = (gift["date"], gift["kind"])
        if gift["kind"] != "meal" and key in seen:
            print("A sponsor is already recorded for", gift["date"].isoformat(), gift["kind"])
            continue
        apply_gift(token, gift)
        if gift["kind"] != "meal":
            seen.add(key)


if __name__ == "__main__":
    main()
