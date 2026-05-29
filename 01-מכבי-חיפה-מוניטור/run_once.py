"""Single-cycle runner for GitHub Actions."""
import os
import logging
from dotenv import load_dotenv
from monitor import run_cycle, send_telegram, load_seen_items, save_seen_items
import hashlib
from datetime import datetime, timezone

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)

groq_api_key   = os.getenv("GROQ_API_KEY")
bot_token      = os.getenv("TELEGRAM_BOT_TOKEN")
chat_id        = os.getenv("TELEGRAM_CHAT_ID")
youtube_api_key = os.getenv("YOUTUBE_API_KEY", "")
tg_api_id      = os.getenv("TELEGRAM_API_ID", "")
tg_api_hash    = os.getenv("TELEGRAM_API_HASH", "")
tg_session     = os.getenv("TELEGRAM_SESSION", "")

if not all([groq_api_key, bot_token, chat_id]):
    logging.error("Missing environment variables.")
    exit(1)

# ── ניטור ערוצי Telegram ────────────────────────────────────────────────────
if tg_api_id and tg_api_hash and tg_session:
    logging.info("Checking Telegram channels...")
    try:
        from telegram_channels import fetch_channel_mentions, format_channel_alert
        hits = fetch_channel_mentions(int(tg_api_id), tg_api_hash, tg_session)

        if hits:
            seen = load_seen_items()
            for hit in hits:
                h = hashlib.md5(hit["link"].encode()).hexdigest()
                if h in seen:
                    continue
                msg = format_channel_alert(hit)
                if send_telegram(bot_token, chat_id, msg):
                    seen[h] = datetime.now(timezone.utc).isoformat()
                    logging.info(f"[TG-CHANNEL] Sent alert from @{hit['channel']}")
            save_seen_items(seen)
        else:
            logging.info("No Maccabi Haifa mentions in Telegram channels.")
    except Exception as e:
        logging.warning(f"Telegram channels check failed: {e}")
else:
    logging.info("TELEGRAM_API_ID/HASH/SESSION not set — skipping channel monitor.")

# ── ריצה רגילה של RSS + Groq ────────────────────────────────────────────────
logging.info("Starting RSS cycle...")
run_cycle(groq_api_key, bot_token, chat_id, youtube_api_key)
logging.info("Done.")
