"""Single-cycle runner for GitHub Actions."""
import os
import logging
from dotenv import load_dotenv
from monitor import run_cycle

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)

groq_api_key = os.getenv("GROQ_API_KEY")
bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
chat_id = os.getenv("TELEGRAM_CHAT_ID")
youtube_api_key = os.getenv("YOUTUBE_API_KEY", "")

if not all([groq_api_key, bot_token, chat_id]):
    logging.error("Missing environment variables.")
    exit(1)

logging.info("Starting single cycle...")
run_cycle(groq_api_key, bot_token, chat_id, youtube_api_key)
logging.info("Done.")
