import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Optional
from urllib.parse import quote_plus

import feedparser
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SEEN_FILE = "seen_items.json"
CYCLE_INTERVAL_SECONDS = 900  # 15 minutes
URGENT_CYCLE_SECONDS = 300        # 5 minutes after urgency=5
MAX_ARTICLE_AGE_HOURS = 25
SEEN_EXPIRY_DAYS = 30
MODEL_ID = "llama-3.3-70b-versatile"
MAX_TOKENS = 4096
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
DAILY_SUMMARY_HOURS = [8, 21]     # Israel time (UTC+3)
IL_UTC_OFFSET = 3

URGENCY_EMOJI = {5: "\U0001f534", 4: "\U0001f7e0", 3: "\U0001f7e1", 2: "\U0001f7e2", 1: "\u26aa"}
RTL = "\u200F"

TYPE_HE = {"IN": "כניסה", "OUT": "יציאה", "RUMOR": "שמועה", "NEGOTIATION": "משא ומתן"}
TYPE_EMOJI = {"IN": "⬅️", "OUT": "➡️", "RUMOR": "💬", "NEGOTIATION": "🤝"}
SIGNAL_HE = {"EARLY": "מוקדם", "CONFIRMED": "מאושר"}
CRED_HE = {"HIGH": "גבוהה", "MEDIUM": "בינונית", "LOW": "נמוכה"}

# Add domains here to block — empty by default
BLACKLISTED_DOMAINS: list = []

TM_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

RSS_FEEDS = [
    # --- English (both directions) ---
    {"url": "https://news.google.com/rss/search?q=Maccabi+Haifa+transfer&hl=en&gl=US&ceid=US:en",      "label": "EN-transfer"},
    {"url": "https://news.google.com/rss/search?q=Maccabi+Haifa+signing&hl=en&gl=US&ceid=US:en",       "label": "EN-signing"},
    {"url": "https://news.google.com/rss/search?q=Maccabi+Haifa+interested&hl=en&gl=US&ceid=US:en",    "label": "EN-interested"},
    {"url": "https://news.google.com/rss/search?q=Maccabi+Haifa+target&hl=en&gl=US&ceid=US:en",        "label": "EN-target"},
    {"url": "https://news.google.com/rss/search?q=Maccabi+Haifa+want&hl=en&gl=US&ceid=US:en",          "label": "EN-want"},
    # שחקן של מכבי חיפה שקבוצה בחו"ל רוצה
    {"url": "https://news.google.com/rss/search?q=%22Maccabi+Haifa%22+%22interested+in%22&hl=en&gl=US&ceid=US:en",  "label": "EN-world-interested"},
    {"url": "https://news.google.com/rss/search?q=%22from+Maccabi+Haifa%22&hl=en&gl=US&ceid=US:en",                 "label": "EN-from-haifa"},
    {"url": "https://news.google.com/rss/search?q=%22Maccabi+Haifa%22+%22linked%22&hl=en&gl=US&ceid=US:en",         "label": "EN-linked"},
    # --- Spanish (Argentina, Spain) ---
    {"url": "https://news.google.com/rss/search?q=Maccabi+Haifa+fichaje&hl=es&gl=ES&ceid=ES:es",       "label": "ES-transfer"},
    {"url": "https://news.google.com/rss/search?q=Maccabi+Haifa+interesa&hl=es&gl=ES&ceid=ES:es",      "label": "ES-interested"},
    {"url": "https://news.google.com/rss/search?q=Maccabi+Haifa+fichaje&hl=es&gl=AR&ceid=AR:es",       "label": "AR-transfer"},
    {"url": "https://news.google.com/rss/search?q=Maccabi+Haifa+interesa&hl=es&gl=AR&ceid=AR:es",      "label": "AR-interested"},
    # --- French ---
    {"url": "https://news.google.com/rss/search?q=Maccabi+Haifa+transfert&hl=fr&gl=FR&ceid=FR:fr",     "label": "FR-transfer"},
    {"url": "https://news.google.com/rss/search?q=Maccabi+Haifa+piste&hl=fr&gl=FR&ceid=FR:fr",         "label": "FR-target"},
    # --- Serbian ---
    {"url": "https://news.google.com/rss/search?q=Maccabi+Haifa+transfer&hl=sr&gl=RS&ceid=RS:sr",      "label": "SR-transfer"},
    {"url": "https://news.google.com/rss/search?q=Maccabi+Haifa&hl=sr&gl=RS&ceid=RS:sr",               "label": "SR-general"},
    # --- Croatian ---
    {"url": "https://news.google.com/rss/search?q=Maccabi+Haifa+transfer&hl=hr&gl=HR&ceid=HR:hr",      "label": "HR-transfer"},
    {"url": "https://news.google.com/rss/search?q=Maccabi+Haifa&hl=hr&gl=HR&ceid=HR:hr",               "label": "HR-general"},
    # --- Bosnian ---
    {"url": "https://news.google.com/rss/search?q=Maccabi+Haifa&hl=bs&gl=BA&ceid=BA:bs",               "label": "BS-general"},
    # --- Portuguese (Brazil) ---
    {"url": "https://news.google.com/rss/search?q=Maccabi+Haifa+transfer&hl=pt-BR&gl=BR&ceid=BR:pt-419", "label": "BR-transfer"},
    {"url": "https://news.google.com/rss/search?q=Maccabi+Haifa+interesse&hl=pt-BR&gl=BR&ceid=BR:pt-419", "label": "BR-interested"},
    # --- Romanian ---
    {"url": "https://news.google.com/rss/search?q=Maccabi+Haifa&hl=ro&gl=RO&ceid=RO:ro",               "label": "RO-general"},
    # --- Georgian ---
    {"url": "https://news.google.com/rss/search?q=Maccabi+Haifa&hl=ka&gl=GE&ceid=GE:ka",               "label": "GE-general"},
    # --- Albanian ---
    {"url": "https://news.google.com/rss/search?q=Maccabi+Haifa&hl=sq&gl=AL&ceid=AL:sq",               "label": "AL-general"},
    # --- Macedonian ---
    {"url": "https://news.google.com/rss/search?q=Maccabi+Haifa&hl=mk&gl=MK&ceid=MK:mk",               "label": "MK-general"},
    # --- Montenegrin ---
    {"url": "https://news.google.com/rss/search?q=Maccabi+Haifa&hl=sr&gl=ME&ceid=ME:sr",               "label": "ME-general"},
    # --- Slovenian ---
    {"url": "https://news.google.com/rss/search?q=Maccabi+Haifa&hl=sl&gl=SI&ceid=SI:sl",               "label": "SI-general"},
    # --- Kosovar ---
    {"url": "https://news.google.com/rss/search?q=Maccabi+Haifa&hl=sq&gl=XK&ceid=XK:sq",               "label": "XK-general"},
    # --- Ukrainian ---
    {"url": "https://news.google.com/rss/search?q=Maccabi+Haifa+transfer&hl=uk&gl=UA&ceid=UA:uk",      "label": "UA-transfer"},
    {"url": "https://news.google.com/rss/search?q=Maccabi+Haifa&hl=uk&gl=UA&ceid=UA:uk",               "label": "UA-general"},
    # --- Polish ---
    {"url": "https://news.google.com/rss/search?q=Maccabi+Haifa+transfer&hl=pl&gl=PL&ceid=PL:pl",      "label": "PL-transfer"},
    {"url": "https://news.google.com/rss/search?q=Maccabi+Haifa&hl=pl&gl=PL&ceid=PL:pl",               "label": "PL-general"},
    # --- Czech ---
    {"url": "https://news.google.com/rss/search?q=Maccabi+Haifa&hl=cs&gl=CZ&ceid=CZ:cs",               "label": "CZ-general"},
    # --- Slovak ---
    {"url": "https://news.google.com/rss/search?q=Maccabi+Haifa&hl=sk&gl=SK&ceid=SK:sk",               "label": "SK-general"},
    # --- Dutch (Netherlands + Belgium) ---
    {"url": "https://news.google.com/rss/search?q=Maccabi+Haifa+transfer&hl=nl&gl=NL&ceid=NL:nl",      "label": "NL-transfer"},
    {"url": "https://news.google.com/rss/search?q=Maccabi+Haifa&hl=nl&gl=NL&ceid=NL:nl",               "label": "NL-general"},
    {"url": "https://news.google.com/rss/search?q=Maccabi+Haifa&hl=nl&gl=BE&ceid=BE:nl",               "label": "BE-general"},
    # --- Turkish ---
    {"url": "https://news.google.com/rss/search?q=Maccabi+Haifa+transfer&hl=tr&gl=TR&ceid=TR:tr",      "label": "TR-transfer"},
    {"url": "https://news.google.com/rss/search?q=Maccabi+Haifa&hl=tr&gl=TR&ceid=TR:tr",               "label": "TR-general"},
    # --- Nigerian (English) ---
    {"url": "https://news.google.com/rss/search?q=Maccabi+Haifa&hl=en&gl=NG&ceid=NG:en",               "label": "NG-general"},
    # --- Ghanaian (English) ---
    {"url": "https://news.google.com/rss/search?q=Maccabi+Haifa&hl=en&gl=GH&ceid=GH:en",               "label": "GH-general"},
    # --- Cameroonian (French) ---
    {"url": "https://news.google.com/rss/search?q=Maccabi+Haifa&hl=fr&gl=CM&ceid=CM:fr",               "label": "CM-general"},
    # --- German ---
    {"url": "https://news.google.com/rss/search?q=Maccabi+Haifa+Transfer&hl=de&gl=DE&ceid=DE:de",      "label": "DE-transfer"},
    {"url": "https://news.google.com/rss/search?q=Maccabi+Haifa&hl=de&gl=DE&ceid=DE:de",               "label": "DE-general"},
    # --- Italian ---
    {"url": "https://news.google.com/rss/search?q=Maccabi+Haifa+trasferimento&hl=it&gl=IT&ceid=IT:it", "label": "IT-transfer"},
    {"url": "https://news.google.com/rss/search?q=Maccabi+Haifa&hl=it&gl=IT&ceid=IT:it",               "label": "IT-general"},
    # --- Greek ---
    {"url": "https://news.google.com/rss/search?q=Maccabi+Haifa&hl=el&gl=GR&ceid=GR:el",               "label": "GR-general"},
    # --- Bulgarian ---
    {"url": "https://news.google.com/rss/search?q=Maccabi+Haifa&hl=bg&gl=BG&ceid=BG:bg",               "label": "BG-general"},
    # --- Hungarian ---
    {"url": "https://news.google.com/rss/search?q=Maccabi+Haifa&hl=hu&gl=HU&ceid=HU:hu",               "label": "HU-general"},
    # --- USA / MLS ---
    {"url": "https://news.google.com/rss/search?q=Maccabi+Haifa+transfer&hl=en&gl=US&ceid=US:en",      "label": "US-transfer"},
    {"url": "https://news.google.com/rss/search?q=Maccabi+Haifa+MLS&hl=en&gl=US&ceid=US:en",           "label": "US-MLS"},
    {"url": "https://news.google.com/rss/search?q=Maccabi+Haifa+interested&hl=en&gl=US&ceid=US:en",    "label": "US-interested"},
    # --- Canadian ---
    {"url": "https://news.google.com/rss/search?q=Maccabi+Haifa&hl=en&gl=CA&ceid=CA:en",               "label": "CA-general"},
    # --- Portuguese (Portugal) ---
    {"url": "https://news.google.com/rss/search?q=Maccabi+Haifa&hl=pt-PT&gl=PT&ceid=PT:pt-150",        "label": "PT-general"},
    # --- Senegalese (French) ---
    {"url": "https://news.google.com/rss/search?q=Maccabi+Haifa&hl=fr&gl=SN&ceid=SN:fr",               "label": "SN-general"},
    # --- Ivory Coast (French) ---
    {"url": "https://news.google.com/rss/search?q=Maccabi+Haifa&hl=fr&gl=CI&ceid=CI:fr",               "label": "CI-general"},
    # --- Russian ---
    {"url": "https://news.google.com/rss/search?q=Maccabi+Haifa&hl=ru&gl=RU&ceid=RU:ru",               "label": "RU-general"},
    # --- Azerbaijani ---
    {"url": "https://news.google.com/rss/search?q=Maccabi+Haifa&hl=az&gl=AZ&ceid=AZ:az",               "label": "AZ-general"},
    # --- Armenian ---
    {"url": "https://news.google.com/rss/search?q=Maccabi+Haifa&hl=hy&gl=AM&ceid=AM:hy",               "label": "AM-general"},
    # --- Official Maccabi Haifa website (WordPress RSS) ---
    {"url": "https://www.maccabi-haifa.co.il/feed/",                                                     "label": "OFFICIAL-site"},
    # --- Google News filtered to official site ---
    {"url": "https://news.google.com/rss/search?q=site:maccabi-haifa.co.il&hl=iw&gl=IL&ceid=IL:iw",    "label": "OFFICIAL-gnews"},
]

SYSTEM_PROMPT = """You are a football transfer intelligence system for Maccabi Haifa FC.
Your PRIMARY mission is to detect EARLY SCOOPS — the first report before it becomes mainstream news.
A confirmed official signing is the LEAST valuable output. The most valuable output is the first rumor or leak nobody else has reported yet.

You receive a list of raw news articles. Your task:

1. PRIORITY ORDER (most important first):
   a. RUMOR — first mention anywhere that Maccabi Haifa is interested in a player
   b. NEGOTIATION — talks ongoing, not yet confirmed
   c. OUT — player linked to leaving before it's official
   d. IN — confirmed signing (less valuable, everyone will know anyway)

2. Keep ALL of the following:
   - Any mention that Maccabi Haifa is "interested in", "targeting", "tracking", "want", "monitoring" a player
   - Any mention of negotiations, talks, meetings between Maccabi Haifa and a player/club
   - Any mention of a player being linked to leaving Maccabi Haifa
   - Confirmed signings and official departures

3. Discard ONLY:
   - Match reports, scores, standings with no transfer angle
   - Pure interviews with no transfer news
   - Stadium, finance, management news with no player transfer angle
   - Articles about FORMER Maccabi Haifa players mentioned only in historical context ("former Maccabi Haifa player", "ex-Maccabi Haifa", "שחקן לשעבר") with NO new transfer link to Maccabi Haifa — these are NOT transfer news
   - Any article where the player's connection to Maccabi Haifa is in the PAST tense only, with no indication of a NEW deal, interest, or negotiation involving Maccabi Haifa now

4. If multiple articles cover the same story, merge into ONE item. Set signal=CONFIRMED only if 2+ independent sources confirm.

5. Return ONLY a raw JSON array — no markdown, no code fences, no explanation.
   If nothing qualifies, return exactly: []

Schema per item:
{
  "title": "concise English title — lead with the scoop angle",
  "summary": "max 2 short factual lines — what is new and who reported it first",
  "player": "player full name or null",
  "type": "IN | OUT | RUMOR | NEGOTIATION",
  "signal": "EARLY | CONFIRMED",
  "sources_count": 1,
  "source": "primary source name",
  "source_headline": "exact original headline of the article that triggered this item — copy verbatim",
  "link": "primary article URL",
  "language": "original language of primary source",
  "credibility": "HIGH | MEDIUM | LOW",
  "urgency": 1,
  "timestamp": "ISO 8601 UTC timestamp of the article"
}

Field rules:
- type: RUMOR=interest/target/link not confirmed, NEGOTIATION=active talks, IN=confirmed joining, OUT=confirmed leaving
- signal: EARLY=first/single source (PREFERRED — this is the scoop), CONFIRMED=2+ independent sources
- credibility: HIGH=known journalist/major outlet, MEDIUM=regional sports media, LOW=anonymous/unverified
- urgency: 5=official announcement, 4=deal agreed, 3=advanced talks, 2=early interest reported, 1=vague unverified link
- Do NOT downgrade urgency just because it is unconfirmed — an early scoop from a credible journalist is urgency=3 even if unconfirmed

CRITICAL — Former player filter:
If a player is described as a "former", "ex-", "לשעבר", "אקס" Maccabi Haifa player, and the article is about their current club or career ELSEWHERE with no active link to Maccabi Haifa now — DO NOT include it. Only include if there is a NEW and ACTIVE transfer connection to Maccabi Haifa in the present tense.
"""


# ---------------------------------------------------------------------------
# Seen-items store
# ---------------------------------------------------------------------------

def load_seen_items() -> dict:
    if not os.path.exists(SEEN_FILE):
        return {}
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def save_seen_items(seen: dict) -> None:
    try:
        with open(SEEN_FILE, "w", encoding="utf-8") as f:
            json.dump(seen, f, indent=2, ensure_ascii=False)
    except OSError as e:
        logging.error(f"Could not save seen_items: {e}")


def expire_seen_items(seen: dict) -> dict:
    cutoff = datetime.now(timezone.utc) - timedelta(days=SEEN_EXPIRY_DAYS)
    pruned = {}
    for h, ts in seen.items():
        if h.startswith("summary_sent_"):
            pruned[h] = ts
            continue
        try:
            dt = datetime.fromisoformat(ts)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt >= cutoff:
                pruned[h] = ts
        except (ValueError, TypeError):
            pass
    removed = len(seen) - len(pruned)
    if removed:
        logging.info(f"Expired {removed} old seen items.")
    return pruned


def compute_hash(player: Optional[str], transfer_type: str, title: str) -> str:
    key = f"{player}-{transfer_type}-{title[:50]}"
    return hashlib.md5(key.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# RSS feed fetching
# ---------------------------------------------------------------------------

def fetch_all_feeds() -> list:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=MAX_ARTICLE_AGE_HOURS)
    articles = []

    for feed_meta in RSS_FEEDS:
        label = feed_meta["label"]
        try:
            result = feedparser.parse(feed_meta["url"])
        except Exception as e:
            logging.warning(f"[{label}] Parse exception: {e}")
            continue

        if result.get("bozo") and not result.get("entries"):
            logging.warning(f"[{label}] Feed parse error (bozo), skipping.")
            continue

        count = 0
        for entry in result.entries:
            pub_parsed = entry.get("published_parsed")
            if pub_parsed:
                try:
                    pub_dt = datetime(*pub_parsed[:6], tzinfo=timezone.utc)
                    if pub_dt < cutoff:
                        continue
                except (TypeError, ValueError):
                    pass

            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            summary = entry.get("summary", entry.get("description", "")).strip()
            published = entry.get("published", "")
            source = result.feed.get("title", label)

            if not title:
                continue

            # Blacklist check
            if any(domain in link for domain in BLACKLISTED_DOMAINS):
                logging.info(f"Blacklisted domain skipped: {link[:60]}")
                continue

            articles.append({
                "title": title,
                "link": link,
                "summary": summary[:200],
                "published": published,
                "source": source,
                "feed_label": label,
            })
            count += 1

        logging.info(f"[{label}] {count} articles within age window.")

    logging.info(f"Total raw articles fetched: {len(articles)}")
    return articles


# ---------------------------------------------------------------------------
# Groq filtering
# ---------------------------------------------------------------------------

def build_prompt(articles: list) -> str:
    lines = [f"Raw articles from the last {MAX_ARTICLE_AGE_HOURS} hours:\n"]
    for i, a in enumerate(articles, 1):
        lines.append(
            f"[{i}]\n"
            f"  TITLE: {a['title']}\n"
            f"  SOURCE: {a['source']}\n"
            f"  PUBLISHED: {a['published']}\n"
            f"  LINK: {a['link']}\n"
            f"  SUMMARY: {a['summary']}\n"
        )
    return "\n".join(lines)


GROQ_BATCH_SIZE = 10  # מקסימום כתבות לבקשה אחת — למנוע 413


def _call_groq_single(groq_api_key: str, articles: list) -> list:
    """שולח אצווה אחת ל-Groq ומחזיר רשימת פריטים."""
    headers = {
        "Authorization": f"Bearer {groq_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL_ID,
        "max_tokens": MAX_TOKENS,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_prompt(articles)},
        ],
    }
    try:
        resp = requests.post(GROQ_API_URL, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logging.error(f"Groq API error: {e}")
        return []

    if raw.startswith("```"):
        lines = raw.split("\n")[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw = "\n".join(lines).strip()

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        logging.error(f"Groq returned non-JSON: {raw[:300]}")
        return []

    if not isinstance(result, list):
        logging.error("Groq response is not a JSON array.")
        return []

    return result


def call_groq(groq_api_key: str, articles: list) -> list:
    if not articles:
        return []

    # חלוקה לאצוות כדי למנוע 413 Payload Too Large
    batches = [articles[i:i + GROQ_BATCH_SIZE] for i in range(0, len(articles), GROQ_BATCH_SIZE)]
    logging.info(f"Sending {len(articles)} articles to Groq in {len(batches)} batch(es).")

    all_results = []
    for idx, batch in enumerate(batches, 1):
        logging.info(f"Groq batch {idx}/{len(batches)} — {len(batch)} articles.")
        items = _call_groq_single(groq_api_key, batch)
        all_results.extend(items)
        if idx < len(batches):
            time.sleep(3)  # מניעת Rate Limit (429) בין אצוות

    logging.info(f"Groq returned {len(all_results)} transfer item(s) total.")
    for i, item in enumerate(all_results, 1):
        logging.info(
            f"[Groq item {i}] player={item.get('player')} type={item.get('type')} "
            f"urgency={item.get('urgency')} source_headline={item.get('source_headline','')!r} "
            f"link={item.get('link','')[:80]}"
        )
    return all_results


# ---------------------------------------------------------------------------
# Player card — Transfermarkt scraping
# ---------------------------------------------------------------------------

def fetch_player_card(player_name: str) -> str:
    try:
        search_url = f"https://www.transfermarkt.com/schnellsuche/ergebnis/schnellsuche?query={quote_plus(player_name)}"
        resp = requests.get(search_url, headers=TM_HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")

        # Find first player result link
        player_link_tag = soup.select_one("table.items tbody tr td.hauptlink a")
        if not player_link_tag:
            return ""

        player_path = player_link_tag.get("href", "")
        if not player_path:
            return ""

        profile_url = f"https://www.transfermarkt.com{player_path}"
        resp2 = requests.get(profile_url, headers=TM_HEADERS, timeout=10)
        soup2 = BeautifulSoup(resp2.text, "html.parser")

        def get_info(label: str) -> str:
            for item in soup2.select("span.info-table__content--regular, span.info-table__content--bold"):
                if label.lower() in item.get_text(strip=True).lower():
                    sibling = item.find_next_sibling()
                    if sibling:
                        return sibling.get_text(strip=True)
            return "—"

        age_tag = soup2.select_one("span[itemprop='birthDate']")
        age = age_tag.get_text(strip=True) if age_tag else "—"

        nationality_tag = soup2.select_one("span[itemprop='nationality']")
        nationality = nationality_tag.get_text(strip=True) if nationality_tag else "—"

        position_tag = soup2.select_one("dd.detail-position__position")
        position = position_tag.get_text(strip=True) if position_tag else "—"

        value_tag = soup2.select_one("a.data-header__market-value-wrapper")
        value = value_tag.get_text(strip=True).split("\n")[0] if value_tag else "—"

        return (
            f"\n{RTL}━━━━━━━━━━━━━━━━\n"
            f"{RTL}📋 *כרטיס שחקן*\n"
            f"{RTL}🌍 לאום: {nationality}\n"
            f"{RTL}📅 תאריך לידה: {age}\n"
            f"{RTL}⚽ פוזיציה: {position}\n"
            f"{RTL}💰 שווי שוק: {value}\n"
            f"{RTL}🔗 [פרופיל Transfermarkt]({profile_url})"
        )
    except Exception as e:
        logging.warning(f"Player card fetch failed for '{player_name}': {e}")
        return ""


# ---------------------------------------------------------------------------
# YouTube highlights
# ---------------------------------------------------------------------------

def fetch_youtube_highlights(player_name: str, youtube_api_key: str) -> str:
    if not youtube_api_key:
        return ""
    try:
        query = quote_plus(f"{player_name} highlights 2026")
        url = (
            f"https://www.googleapis.com/youtube/v3/search"
            f"?part=snippet&q={query}&type=video&maxResults=1&key={youtube_api_key}"
        )
        resp = requests.get(url, timeout=10)
        data = resp.json()
        items = data.get("items", [])
        if not items:
            return ""
        video_id = items[0]["id"]["videoId"]
        return f"https://youtu.be/{video_id}"
    except Exception as e:
        logging.warning(f"YouTube fetch failed for '{player_name}': {e}")
        return ""


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------

def format_telegram_message(item: dict, player_card: str = "", youtube_url: str = "") -> str:
    urgency = item.get("urgency", 1)
    emoji = URGENCY_EMOJI.get(urgency, "\u26aa")
    title = item.get("title", "Transfer Update")
    summary = item.get("summary", "")
    transfer_type = item.get("type", "")
    signal = item.get("signal", "")
    credibility = item.get("credibility", "")
    source_name = item.get("source", "Unknown")
    source_headline = item.get("source_headline", "")
    link = item.get("link", "")
    timestamp = item.get("timestamp", "")
    player = item.get("player")

    type_str = TYPE_HE.get(transfer_type, transfer_type)
    type_emoji = TYPE_EMOJI.get(transfer_type, "")
    signal_str = SIGNAL_HE.get(signal, signal)
    cred_str = CRED_HE.get(credibility, credibility)
    player_line = f"{RTL}👤 שחקן: *{player}*" if player else None

    lines = [
        f"{RTL}*{title}*",
        player_line,
        f"{RTL}{summary}",
        "",
        f"{RTL}סוג: `{type_str}`",
        f"{RTL}אות: `{signal_str}`",
        f"{RTL}אמינות: `{cred_str}`",
        f"{RTL}דחיפות: {urgency}/5",
        f"{RTL}מקור: [{source_name}]({link})",
        f"{RTL}📰 כותרת מקורית: _{source_headline}_" if source_headline else None,
        f"{RTL}זמן: {timestamp}",
    ]

    if youtube_url:
        lines.append(f"{RTL}[צפה בהייליטס]({youtube_url})")

    if player_card:
        lines.append(player_card)

    return "\n".join(line for line in lines if line is not None)


def send_telegram(bot_token: str, chat_id: str, text: str) -> bool:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            return True
        logging.warning(f"Telegram API error {resp.status_code}: {resp.text[:200]}")
        return False
    except requests.RequestException as e:
        logging.error(f"Telegram request failed: {e}")
        return False


# ---------------------------------------------------------------------------
# Daily summary
# ---------------------------------------------------------------------------

def maybe_send_daily_summary(bot_token: str, chat_id: str, seen: dict) -> None:
    now_il = datetime.now(timezone.utc) + timedelta(hours=IL_UTC_OFFSET)
    if now_il.hour not in DAILY_SUMMARY_HOURS:
        return

    summary_key = f"summary_sent_{now_il.strftime('%Y-%m-%d-%H')}"
    if summary_key in seen:
        return  # Already sent this hour

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    recent_titles = []

    for h, ts in seen.items():
        if h.startswith("summary_sent_"):
            continue
        try:
            dt = datetime.fromisoformat(ts)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt >= cutoff:
                # We only stored hash+timestamp, not title — so we show count
                recent_titles.append(ts)
        except (ValueError, TypeError):
            pass

    count = len(recent_titles)
    greeting = "בוקר טוב! ☀️" if now_il.hour == 8 else "ערב טוב! 🌙"

    if count == 0:
        body = f"{RTL}אין ידיעות העברות חדשות ב-24 השעות האחרונות."
    else:
        body = f"{RTL}סה\"כ {count} ידיעת/ידיעות העברות נשלחו ב-24 השעות האחרונות."

    msg = (
        f"{RTL}\U0001f4ca *סיכום יומי — מכבי חיפה*\n"
        f"{RTL}{greeting}\n"
        f"{RTL}{body}"
    )

    success = send_telegram(bot_token, chat_id, msg)
    if success:
        seen[summary_key] = datetime.now(timezone.utc).isoformat()
        logging.info(f"Daily summary sent ({count} items).")


# ---------------------------------------------------------------------------
# Main cycle
# ---------------------------------------------------------------------------

def run_cycle(groq_api_key: str, bot_token: str, chat_id: str, youtube_api_key: str) -> bool:
    """Returns True if any urgency=5 item was sent (triggers shorter sleep)."""
    logging.info("--- Cycle start ---")

    seen = load_seen_items()
    seen = expire_seen_items(seen)

    # Daily summary check
    maybe_send_daily_summary(bot_token, chat_id, seen)

    articles = fetch_all_feeds()
    if not articles:
        logging.info("No articles found. Skipping Groq call.")
        save_seen_items(seen)
        return False

    filtered = call_groq(groq_api_key, articles)
    if not filtered:
        logging.info("No transfer items after filtering.")
        save_seen_items(seen)
        return False

    new_count = 0
    had_urgent = False

    for item in filtered:
        player = item.get("player")
        transfer_type = item.get("type", "")
        title = item.get("title", "")
        urgency = item.get("urgency", 1)

        h = compute_hash(player, transfer_type, title)
        if h in seen:
            logging.info(f"Duplicate skipped: {title[:60]}")
            continue

        # Fetch enrichment data
        player_card = fetch_player_card(player) if player else ""
        youtube_url = fetch_youtube_highlights(player, youtube_api_key) if player else ""

        msg = format_telegram_message(item, player_card=player_card, youtube_url=youtube_url)
        success = send_telegram(bot_token, chat_id, msg)

        if success:
            seen[h] = datetime.now(timezone.utc).isoformat()
            new_count += 1
            if urgency == 5:
                had_urgent = True
            logging.info(f"Sent (urgency={urgency}): {title[:60]}")
            time.sleep(1)
        else:
            logging.warning(f"Failed to send: {title[:60]}")

    save_seen_items(seen)
    logging.info(f"--- Cycle complete. {new_count} new item(s) sent. ---")
    return had_urgent


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    load_dotenv()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )

    groq_api_key = os.getenv("GROQ_API_KEY")
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    youtube_api_key = os.getenv("YOUTUBE_API_KEY", "")  # optional

    missing = [k for k, v in {
        "GROQ_API_KEY": groq_api_key,
        "TELEGRAM_BOT_TOKEN": bot_token,
        "TELEGRAM_CHAT_ID": chat_id,
    }.items() if not v]

    if missing:
        logging.error(f"Missing environment variables: {', '.join(missing)}")
        logging.error("Copy .env.example to .env and fill in your credentials.")
        return

    if not youtube_api_key:
        logging.warning("YOUTUBE_API_KEY not set — YouTube highlights disabled.")

    logging.info("Maccabi Haifa Transfer Monitor started. Running every hour.")

    while True:
        try:
            had_urgent = run_cycle(groq_api_key, bot_token, chat_id, youtube_api_key)
        except Exception as e:
            logging.error(f"Unexpected error in cycle: {e}")
            had_urgent = False

        sleep_time = URGENT_CYCLE_SECONDS if had_urgent else CYCLE_INTERVAL_SECONDS
        if had_urgent:
            logging.info("Urgency=5 detected — next cycle in 5 minutes.")
        logging.info(f"Sleeping {sleep_time}s until next cycle...")
        time.sleep(sleep_time)


if __name__ == "__main__":
    main()
