#!/usr/bin/env python3
"""Watches dubizzle.com Motors search pages and notifies on new ads.

Config: watchlist.json (list of searches to watch).
State:  state/seen.json (ad IDs already notified about, persisted in git).
"""
import argparse
import json
import os
import re
import smtplib
import sys
import urllib.parse
import urllib.request
from email.mime.text import MIMEText
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).parent
WATCHLIST_FILE = ROOT / "watchlist.json"
STATE_FILE = ROOT / "state" / "seen.json"

LISTING_HREF_RE = re.compile(r"/motors/used-cars/[^\"'#?]+---([0-9a-f]{16,32})/?")
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
PRICE_RE = re.compile(r"AED\s*([\d,]{4,})|([\d,]{4,})\s*AED", re.IGNORECASE)
CITY_KEYWORDS = [
    "Dubai", "Abu Dhabi", "Sharjah", "Ajman", "Fujairah",
    "Ras Al Khaimah", "Umm Al Quwain", "Al Ain",
]


def load_json(path, default):
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")


def extract_year(text):
    match = YEAR_RE.search(text)
    return int(match.group(0)) if match else None


def extract_price(text):
    match = PRICE_RE.search(text)
    if not match:
        return None
    digits = match.group(1) or match.group(2)
    return int(digits.replace(",", ""))


def extract_city(text):
    for city in CITY_KEYWORDS:
        if city in text:
            return city
    return None


def is_blocked(html):
    return "Pardon Our Interruption" in html or "Incapsula" in html[:2000]


def scraperapi_request(url, api_key, render):
    params = {"api_key": api_key, "url": url, "premium": "true"}
    if render:
        params["render"] = "true"
    request_url = f"https://api.scraperapi.com/?{urllib.parse.urlencode(params)}"
    timeout = 90 if render else 60

    last_error = None
    for attempt in range(2):
        try:
            with urllib.request.urlopen(request_url, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            last_error = e
    raise last_error


def fetch_html(url):
    api_key = os.environ.get("SCRAPERAPI_KEY")
    if not api_key:
        raise RuntimeError("SCRAPERAPI_KEY is not set")

    # Try the fast (non-rendered) request first; only pay for JS rendering
    # if the plain fetch actually gets challenged.
    html = scraperapi_request(url, api_key, render=False)
    if is_blocked(html):
        html = scraperapi_request(url, api_key, render=True)
        if is_blocked(html):
            raise RuntimeError(f"blocked by anti-bot protection at {url}")
    return html


def parse_ads(html, base_url):
    soup = BeautifulSoup(html, "html.parser")
    ads = {}
    for anchor in soup.select("a[href*='/motors/used-cars/']"):
        href = anchor.get("href") or ""
        match = LISTING_HREF_RE.search(href)
        if not match:
            continue
        ad_id = match.group(1)
        if ad_id in ads:
            continue

        container = anchor
        for _ in range(4):
            if container.parent is None or container.name in ("li", "article"):
                break
            container = container.parent

        text = " ".join(container.get_text(" ", strip=True).split())
        full_url = urllib.parse.urljoin(base_url, href)
        ads[ad_id] = {
            "id": ad_id,
            "url": full_url,
            "title": text[:120],
            "text": text,
            "year": extract_year(text),
            "price": extract_price(text),
            "city": extract_city(text),
        }
    return ads


def scrape_search(check):
    url = check["url"]
    max_pages = check.get("max_pages", 2)
    all_ads = {}
    for page_num in range(1, max_pages + 1):
        page_url = url if page_num == 1 else f"{url.rstrip('/')}/?page={page_num}"
        html = fetch_html(page_url)
        ads = parse_ads(html, page_url)
        if not ads:
            break
        all_ads.update(ads)
    return all_ads


def passes_filters(ad, check):
    min_year = check.get("min_year")
    max_year = check.get("max_year")
    min_price = check.get("min_price")
    max_price = check.get("max_price")
    keyword = check.get("keyword")

    if keyword and keyword.lower() not in ad["text"].lower():
        return False
    if min_year is not None and ad["year"] is not None and ad["year"] < min_year:
        return False
    if max_year is not None and ad["year"] is not None and ad["year"] > max_year:
        return False
    if min_price is not None and ad["price"] is not None and ad["price"] < min_price:
        return False
    if max_price is not None and ad["price"] is not None and ad["price"] > max_price:
        return False
    return True


def format_message(check_name, ad):
    lines = [f"New ad: {check_name}", ad["title"]]
    details = []
    if ad["price"] is not None:
        details.append(f"{ad['price']:,} AED")
    if ad["year"] is not None:
        details.append(str(ad["year"]))
    if ad["city"]:
        details.append(ad["city"])
    if details:
        lines.append(" | ".join(details))
    lines.append(ad["url"])
    return "\n".join(lines)


def send_email(subject, body):
    address = os.environ.get("GMAIL_ADDRESS")
    app_password = os.environ.get("GMAIL_APP_PASSWORD")
    to_addr = os.environ.get("NOTIFY_EMAIL_TO", address)
    if not address or not app_password:
        return

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = address
    msg["To"] = to_addr

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(address, app_password)
        server.sendmail(address, [to_addr], msg.as_string())


def send_whatsapp(text):
    phone = os.environ.get("CALLMEBOT_PHONE")
    api_key = os.environ.get("CALLMEBOT_APIKEY")
    if not phone or not api_key:
        return

    params = urllib.parse.urlencode({"phone": phone, "text": text, "apikey": api_key})
    request_url = f"https://api.callmebot.com/whatsapp.php?{params}"
    with urllib.request.urlopen(request_url, timeout=20) as resp:
        resp.read()


def notify(check_name, ad):
    message = format_message(check_name, ad)
    try:
        send_email(f"Dubizzle: new ad - {check_name}", message)
    except Exception as e:
        print(f"[warn] email notification failed: {e}", file=sys.stderr)
    try:
        send_whatsapp(message)
    except Exception as e:
        print(f"[warn] whatsapp notification failed: {e}", file=sys.stderr)


def run_test_notification():
    ad = {
        "id": "test",
        "url": "https://uae.dubizzle.com/",
        "title": "This is a test notification from dubizzle-monitor",
        "text": "test",
        "year": None,
        "price": None,
        "city": None,
    }
    print("[info] sending test notification (email + whatsapp if configured)")
    notify("Test", ad)
    print("[info] done. Check your inbox/WhatsApp.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="send a test notification and exit")
    args = parser.parse_args()

    if args.test:
        run_test_notification()
        return

    watchlist = load_json(WATCHLIST_FILE, {"checks": []})
    state = load_json(STATE_FILE, {})
    state_changed = False

    for check in watchlist.get("checks", []):
        name = check["name"]
        print(f"[info] checking: {name}")
        try:
            ads = scrape_search(check)
        except Exception as e:
            print(f"[error] {name}: {e}", file=sys.stderr)
            continue

        seen_ids = set(state.get(name, []))
        is_first_run = name not in state
        new_ads = [ad for ad_id, ad in ads.items() if ad_id not in seen_ids]

        if not is_first_run:
            for ad in new_ads:
                if passes_filters(ad, check):
                    print(f"[info] new ad matched: {ad['url']}")
                    notify(name, ad)
        else:
            print(f"[info] first run for '{name}', baselining {len(ads)} ads without notifying")

        state[name] = sorted(set(ads.keys()) | seen_ids)
        state_changed = True

    if state_changed:
        save_json(STATE_FILE, state)


if __name__ == "__main__":
    main()
