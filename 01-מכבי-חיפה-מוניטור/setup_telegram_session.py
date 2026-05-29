# -*- coding: utf-8 -*-
"""
הרץ פעם אחת בלבד כדי לקבל את מחרוזת ה-Session
לאחר מכן הוסף את הפלט ל-.env תחת TELEGRAM_SESSION
"""
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID   = int(input("הכנס api_id: ").strip())
API_HASH = input("הכנס api_hash: ").strip()

async def main():
    async with TelegramClient(StringSession(), API_ID, API_HASH) as client:
        session_string = client.session.save()
        print("\n" + "="*60)
        print("הוסף לקובץ .env את השורה הבאה:")
        print(f"TELEGRAM_SESSION={session_string}")
        print("="*60)
        print("ולסיקרטס של GitHub הוסף:")
        print(f"TELEGRAM_SESSION = {session_string[:30]}...")

asyncio.run(main())
