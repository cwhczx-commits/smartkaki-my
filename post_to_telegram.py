"""
post_to_telegram.py
====================
Reads coupons.json and posts a digest of today's deals to the SmartKaki MY
Telegram channel via the Telegram Bot API.

Only posts if the deal list actually changed since the last post (tracked
via a hash file committed alongside coupons.json) — so the channel doesn't
get the same message every single day when nothing's new.

Requires two environment variables:
  TELEGRAM_BOT_TOKEN   - from @BotFather
  TELEGRAM_CHAT_ID     - e.g. "@smartkakimy" for a public channel
                          (the bot must be an admin of the channel with
                          "Post Messages" permission)
"""

import hashlib
import json
import os
import sys

import requests

COUPONS_FILE = "coupons.json"
HASH_FILE = ".telegram_last_hash.txt"
MAX_DEALS_IN_POST = 8
SITE_URL = "https://smartkaki-my.vercel.app"  # update if you're on a custom domain


def load_deals():
    with open(COUPONS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("deals", []), data.get("updated_at")


def deals_fingerprint(deals):
    # Hash on the fields a reader would actually notice changing.
    # Re-running the same 8 offers with the same rates won't re-trigger a post.
    parts = sorted(
        f"{d.get('id')}:{d.get('commission')}:{d.get('voucher_code')}"
        for d in deals
    )
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def previous_fingerprint():
    if os.path.exists(HASH_FILE):
        with open(HASH_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    return None


def escape_html(text):
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_message(deals):
    lines = ["<b>SmartKaki MY — Today's Deals</b>", ""]
    for d in deals[:MAX_DEALS_IN_POST]:
        name = escape_html(d.get("name", "Deal"))
        code = d.get("voucher_code")
        commission = d.get("commission")
        headline = f"Code: {escape_html(code)}" if code else (commission or "Official partner link")
        lines.append(f"• <b>{name}</b> — {escape_html(headline)}\n  {d.get('url')}")
    lines.append("")
    lines.append(f"More deals: {SITE_URL}")
    return "\n".join(lines)


def send_telegram_message(token, chat_id, text):
    resp = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("Missing TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID env vars", file=sys.stderr)
        sys.exit(1)

    deals, updated_at = load_deals()
    if not deals:
        print("No deals in coupons.json — skipping post")
        return

    current_fp = deals_fingerprint(deals)
    if current_fp == previous_fingerprint():
        print("Deals unchanged since last post — skipping to avoid duplicate spam")
        return

    message = build_message(deals)
    send_telegram_message(token, chat_id, message)

    with open(HASH_FILE, "w", encoding="utf-8") as f:
        f.write(current_fp)

    print(f"Posted digest of {min(len(deals), MAX_DEALS_IN_POST)} deals (updated_at={updated_at})")


if __name__ == "__main__":
    main()
