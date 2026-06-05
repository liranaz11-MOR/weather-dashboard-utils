# -*- coding: utf-8 -*-
"""
האזנה לערוצי Telegram של עיתונאי העברות
מחפש אזכורים של מכבי חיפה ושולח התראה מיידית
"""
import asyncio
import logging
import os
from datetime import datetime, timezone, timedelta

from telethon import TelegramClient
from telethon.sessions import StringSession

# ── ערוצים לניטור ────────────────────────────────────────────────────────────
CHANNELS = [
    "FabrizioRomanoTG",       # Fabrizio Romano — ה-"Here We Go" הגדול
    "transfer_news_football",  # Transfer News Football — אגרגטור עולמי
    "SkySportsNews",           # Sky Sports — מאשר עסקאות
    "BBCSport",                # BBC Sport
]

# ── מילות חיפוש ──────────────────────────────────────────────────────────────
KEYWORDS = [
    "maccabi haifa",
    "מכבי חיפה",
    "maccaby haifa",
    "makabi haifa",
    "haifa fc",
    "haifa maccabi",
]

MAX_HOURS = 1  # כמה שעות אחורה לסרוק בכל ריצה


async def _fetch(api_id: int, api_hash: str, session_str: str) -> list:
    client = TelegramClient(StringSession(session_str), api_id, api_hash)
    await client.connect()

    cutoff = datetime.now(timezone.utc) - timedelta(hours=MAX_HOURS)
    results = []

    for channel in CHANNELS:
        try:
            async for msg in client.iter_messages(channel, limit=100):
                if msg.date.replace(tzinfo=timezone.utc) < cutoff:
                    break
                text = (msg.text or msg.message or "").strip()
                if not text:
                    continue
                if any(kw.lower() in text.lower() for kw in KEYWORDS):
                    results.append({
                        "channel": channel,
                        "text": text[:600],
                        "date": msg.date.isoformat(),
                        "link": f"https://t.me/{channel}/{msg.id}",
                    })
                    logging.info(f"[TG-CHANNEL] Hit in @{channel}: {text[:80]}")
        except Exception as e:
            logging.warning(f"[TG-CHANNEL] Error reading @{channel}: {e}")

    await client.disconnect()
    return results


def fetch_channel_mentions(api_id: int, api_hash: str, session_str: str) -> list:
    """Entry point — sync wrapper."""
    try:
        return asyncio.run(_fetch(api_id, api_hash, session_str))
    except Exception as e:
        logging.error(f"[TG-CHANNEL] Fatal error: {e}")
        return []


def format_channel_alert(hit: dict) -> str:
    from monitor import RTL
    channel = hit["channel"]
    text = hit["text"]
    link = hit["link"]
    date = hit["date"][:16].replace("T", " ")
    return (
        f"{RTL}📡 *סקופ מטלגרם — @{channel}*\n\n"
        f"{RTL}{text}\n\n"
        f"{RTL}🕐 {date}\n"
        f"{RTL}🔗 [פתח בטלגרם]({link})"
    )
