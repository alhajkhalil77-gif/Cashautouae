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

ROOT = Path(__file__).parent
WATCHLIST_FILE = ROOT / "watchlist.json"
STATE_FILE = ROOT / "state" / "seen.json"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

LISTING_HREF_RE = re.compile(r"/motors/used-cars/[^\"'#?]+---([0-9a-f]{16,32})/?")
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
PRICE_RE = re.compile(r"AED\s*([\d,]+)", re.IGNORECASE)
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
    return int(match.group(1).replace(",", ""))


def extract_city(text):
    for city in CITY_KEYWORDS:
        if city in text:
            return city
    return None


def scrape_page(page, url):
    page.goto(url, wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(4000)

    title = page.title()
    if "Pardon Our Interruption" in title or "Incapsula" in page.content()[:500]:
        raise RuntimeError(f"blocked by anti-bot protection at {url}")

    anchors = page.eval_on_selector_all(
        "a[href*='/motors/used-cars/']",
        """els => els.map(el => {
            const container = el.closest("li, article, div[class*='listing'], div[role='listitem']") || el;
            return { href: el.getAttribute('href'), text: container.innerText || el.innerText || '' };
        })""",
    )

    ads = {}
    for item in anchors:
        href = item.get("href") or ""
        match = LISTING_HREF_RE.search(href)
        if not match:
            continue
        ad_id = match.group(1)
        if ad_id in ads:
            continue
        full_url = urllib.parse.urljoin(url, href)
        text = " ".join((item.get("text") or "").split())
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


def scrape_search(browser, check):
    url = check["url"]
    max_pages = check.get("max_pages", 2)
    all_ads = {}
    context = browser.new_context(user_agent=USER_AGENT, locale="en-US")
    page = context.new_page()
    try:
        for page_num in range(1, max_pages + 1):
            page_url = url if page_num == 1 else f"{url.rstrip('/')}/?page={page_num}"
            ads = scrape_page(page, page_url)
            if not ads:
                break
            all_ads.update(ads)
    finally:
        context.close()
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

    from playwright.sync_api import sync_playwright

    watchlist = load_json(WATCHLIST_FILE, {"checks": []})
    state = load_json(STATE_FILE, {})
    state_changed = False

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            for check in watchlist.get("checks", []):
                name = check["name"]
                print(f"[info] checking: {name}")
                try:
                    ads = scrape_search(browser, check)
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
        finally:
            browser.close()

    if state_changed:
        save_json(STATE_FILE, state)


if __name__ == "__main__":
    main()
