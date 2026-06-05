# -*- coding: utf-8 -*-
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID   = 35196504
API_HASH = "f4a884b0f5c74358c22621d60f7216d0"

async def main():
    async with TelegramClient(StringSession(), API_ID, API_HASH) as client:
        session_string = client.session.save()
        print("\n" + "="*60)
        print("TELEGRAM_SESSION=" + session_string)
        print("="*60)

asyncio.run(main())
