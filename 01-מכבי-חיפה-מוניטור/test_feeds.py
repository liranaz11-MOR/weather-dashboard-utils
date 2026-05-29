"""בדיקת פיד ו-Groq מקומית"""
import os, sys
sys.path.insert(0, '.')
from dotenv import load_dotenv
load_dotenv()

from monitor import fetch_all_feeds, call_groq

print("=== שליפת כתבות מ-RSS ===")
arts = fetch_all_feeds()
print(f"סה\"כ כתבות: {len(arts)}")

he = [a for a in arts if any('א' <= c <= 'ת' for c in a['title'])]
en = [a for a in arts if not any('א' <= c <= 'ת' for c in a['title'])]
print(f"  עברית: {len(he)}")
print(f"  לועזית: {len(en)}")
print()

print("--- 15 כתבות ראשונות ---")
for a in arts[:15]:
    print(f"[{a['feed_label']}] {a['title'][:90]}")

print()
print("=== שליחה ל-Groq ===")
key = os.getenv("GROQ_API_KEY")
if not key:
    print("ERROR: GROQ_API_KEY לא מוגדר ב-.env")
    sys.exit(1)

# שלח רק 30 כתבות ראשונות לחסוך tokens
result = call_groq(key, arts[:30])
print(f"Groq החזיר: {len(result)} פריטים")
for item in result:
    print(f"  -> [{item.get('type')}] urgency={item.get('urgency')} | {item.get('title','')[:70]}")
    print(f"     source_headline: {item.get('source_headline','')[:70]}")
