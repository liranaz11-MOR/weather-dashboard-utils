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
    # ── English ──────────────────────────────────────────────────────────────
    # signing / arrival
    {"url": "https://news.google.com/rss/search?q=%22Maccabi+Haifa%22+%28transfer+OR+signing+OR+sign+OR+signs+OR+signed+OR+joins+OR+join%29&hl=en&gl=US&ceid=US:en",
     "label": "EN-sign"},
    # interest / pursuit
    {"url": "https://news.google.com/rss/search?q=%22Maccabi+Haifa%22+%28interested+OR+interest+OR+keen+OR+want+OR+wants+OR+target+OR+tracking+OR+monitoring+OR+pursuit%29&hl=en&gl=US&ceid=US:en",
     "label": "EN-interest"},
    # deal mechanics
    {"url": "https://news.google.com/rss/search?q=%22Maccabi+Haifa%22+%28bid+OR+offer+OR+deal+OR+loan+OR+linked+OR+approach+OR+negotiations+OR+contract+OR+agreement+OR+move%29&hl=en&gl=US&ceid=US:en",
     "label": "EN-deal"},
    # departure
    {"url": "https://news.google.com/rss/search?q=%22Maccabi+Haifa%22+%28departure+OR+leaves+OR+departs+OR+exit+OR+sold+OR+released+OR+from+Maccabi+Haifa%29&hl=en&gl=US&ceid=US:en",
     "label": "EN-out"},
    # MLS / North America angle
    {"url": "https://news.google.com/rss/search?q=%22Maccabi+Haifa%22+%28MLS+OR+NYCFC+OR+Inter+Miami+OR+LA+Galaxy%29&hl=en&gl=US&ceid=US:en",
     "label": "EN-MLS"},

    # ── Spanish — Spain + Argentina ──────────────────────────────────────────
    {"url": "https://news.google.com/rss/search?q=%22Maccabi+Haifa%22+%28fichaje+OR+interesa+OR+interesado+OR+quiere+OR+oferta+OR+traspaso+OR+prestamo+OR+negocia+OR+acuerdo+OR+firma+OR+vinculado+OR+seguimiento+OR+contrata+OR+cedido%29&hl=es&gl=ES&ceid=ES:es",
     "label": "ES-all"},
    {"url": "https://news.google.com/rss/search?q=%22Maccabi+Haifa%22+%28fichaje+OR+interesa+OR+interesado+OR+quiere+OR+oferta+OR+traspaso+OR+prestamo+OR+negocia+OR+acuerdo+OR+firma+OR+vinculado%29&hl=es&gl=AR&ceid=AR:es",
     "label": "AR-all"},

    # ── French — France + Senegal + Cameroon ────────────────────────────────
    {"url": "https://news.google.com/rss/search?q=%22Maccabi+Haifa%22+%28transfert+OR+int%C3%A9ress%C3%A9+OR+veut+OR+offre+OR+n%C3%A9gocie+OR+accord+OR+signe+OR+pr%C3%AAt+OR+piste+OR+recrute+OR+cible+OR+arrive+OR+part%29&hl=fr&gl=FR&ceid=FR:fr",
     "label": "FR-all"},
    {"url": "https://news.google.com/rss/search?q=%22Maccabi+Haifa%22+%28transfert+OR+int%C3%A9ress%C3%A9+OR+offre+OR+accord+OR+piste+OR+recrute%29&hl=fr&gl=SN&ceid=SN:fr",
     "label": "SN-all"},
    {"url": "https://news.google.com/rss/search?q=%22Maccabi+Haifa%22+%28transfert+OR+int%C3%A9ress%C3%A9+OR+offre+OR+accord+OR+piste%29&hl=fr&gl=CM&ceid=CM:fr",
     "label": "CM-all"},

    # ── Serbian ──────────────────────────────────────────────────────────────
    {"url": "https://news.google.com/rss/search?q=%22Maccabi+Haifa%22+%28transfer+OR+poja%C4%8Danje+OR+zainteresovan+OR+pregovori+OR+posudba+OR+ugovor+OR+dolazi+OR+odlazi+OR+potpisuje%29&hl=sr&gl=RS&ceid=RS:sr",
     "label": "SR-all"},

    # ── Croatian ─────────────────────────────────────────────────────────────
    {"url": "https://news.google.com/rss/search?q=%22Maccabi+Haifa%22+%28transfer+OR+poja%C4%8Danje+OR+zainteresiran+OR+pregovori+OR+posudba+OR+ugovor+OR+dolazi+OR+odlazi%29&hl=hr&gl=HR&ceid=HR:hr",
     "label": "HR-all"},

    # ── Portuguese — Brazil ──────────────────────────────────────────────────
    {"url": "https://news.google.com/rss/search?q=%22Maccabi+Haifa%22+%28transfer+OR+interesse+OR+contrata+OR+refor%C3%A7o+OR+proposta+OR+negocia%C3%A7%C3%A3o+OR+empr%C3%A9stimo+OR+acordo+OR+assina%29&hl=pt-BR&gl=BR&ceid=BR:pt-419",
     "label": "BR-all"},

    # ── German ───────────────────────────────────────────────────────────────
    {"url": "https://news.google.com/rss/search?q=%22Maccabi+Haifa%22+%28Transfer+OR+Interesse+OR+interessiert+OR+Angebot+OR+Verhandlung+OR+Leihe+OR+Wechsel+OR+verpflichtet+OR+Ablöse%29&hl=de&gl=DE&ceid=DE:de",
     "label": "DE-all"},

    # ── Italian ──────────────────────────────────────────────────────────────
    {"url": "https://news.google.com/rss/search?q=%22Maccabi+Haifa%22+%28trasferimento+OR+interesse+OR+interessato+OR+offerta+OR+trattativa+OR+prestito+OR+accordo+OR+firma+OR+acquisto+OR+cessione%29&hl=it&gl=IT&ceid=IT:it",
     "label": "IT-all"},

    # ── Turkish ──────────────────────────────────────────────────────────────
    {"url": "https://news.google.com/rss/search?q=%22Maccabi+Haifa%22+%28transfer+OR+ilgileniyor+OR+teklif+OR+anla%C5%9Fma+OR+kiral%C4%B1k+OR+imzalad%C4%B1+OR+ayr%C4%B1l%C4%B1yor%29&hl=tr&gl=TR&ceid=TR:tr",
     "label": "TR-all"},

    # ── Ukrainian ────────────────────────────────────────────────────────────
    {"url": "https://news.google.com/rss/search?q=%22Maccabi+Haifa%22+%28transfer+OR+%D1%82%D1%80%D0%B0%D0%BD%D1%81%D1%84%D0%B5%D1%80+OR+%D1%96%D0%BD%D1%82%D0%B5%D1%80%D0%B5%D1%81+OR+%D0%BF%D0%B5%D1%80%D0%B5%D0%B3%D0%BE%D0%B2%D0%BE%D1%80%D0%B8+OR+%D0%BE%D1%80%D0%B5%D0%BD%D0%B4%D0%B0%29&hl=uk&gl=UA&ceid=UA:uk",
     "label": "UA-all"},

    # ── Polish ───────────────────────────────────────────────────────────────
    {"url": "https://news.google.com/rss/search?q=%22Maccabi+Haifa%22+%28transfer+OR+zainteresowanie+OR+oferta+OR+negocjacje+OR+wypo%C5%BCyczenie+OR+umowa%29&hl=pl&gl=PL&ceid=PL:pl",
     "label": "PL-all"},

    # ── Official Maccabi Haifa website — direct RSS (bypasses Groq) ──────────
    {"url": "https://www.maccabi-haifa.co.il/feed/",                            "label": "OFFICIAL-site"},
]

SYSTEM_PROMPT = """You are a football transfer intelligence system for Maccabi Haifa FC.
Your mission: detect REAL transfer news only — signings, departures, active negotiations, or credible interest in a specific named player.

STRICT RULES — when in doubt, DISCARD:

INCLUDE only if ALL conditions are met:
1. The article is about a SPECIFIC named player (not general squad/roster news)
2. There is an ACTIVE and CURRENT transfer action: signing, departure, loan, negotiation, or named interest
3. The connection to Maccabi Haifa is in the PRESENT or FUTURE tense — not historical

DISCARD everything else, including:
- Match reports, scores, league standings, cup results
- Squad previews, season reviews, training news
- Interviews with no transfer content
- Stadium, finance, ownership, coaching staff news
- Any article about a former/ex Maccabi Haifa player with no active new link to the club
- Vague articles ("Maccabi Haifa could be interested", "rumored to monitor") with no named player
- Articles that mention Maccabi Haifa only in passing or as opponent

If multiple articles cover the same story, merge into ONE item.
If nothing qualifies, return exactly: []
Return ONLY a raw JSON array — no markdown, no code fences.

Schema per item:
{
  "title": "concise English title",
  "summary": "1-2 factual lines: who, what action, which clubs",
  "player": "full player name",
  "type": "IN | OUT | RUMOR | NEGOTIATION",
  "signal": "EARLY | CONFIRMED",
  "sources_count": 1,
  "source": "source outlet name",
  "source_headline": "exact original headline verbatim",
  "link": "article URL",
  "language": "article language",
  "credibility": "HIGH | MEDIUM | LOW",
  "urgency": 2,
  "timestamp": "ISO 8601 UTC"
}

urgency scale: 5=official announcement, 4=deal agreed/done, 3=advanced talks, 2=credible named interest or early rumor from known journalist, 1=vague/anonymous (DO NOT return urgency=1 items)
credibility: HIGH=verified journalist or major outlet, MEDIUM=regional sports media, LOW=blog/unverified
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
MIN_URGENCY = 2       # לא שולחים urgency=1 — רעש בלבד

# מילות מפתח להודעות רשמיות של המועדון (עוקפות Groq)
OFFICIAL_KEYWORDS = [
    "חתם", "הצטרף", "כניסה", "העברה", "הלוואה", "השאלה", "חידש", "הסכם",
    "עזב", "פרידה", "מכרנו", "transfer", "signing", "joins", "signed",
    "loan", "contract", "departure", "extends",
]


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
# Official site — direct pipeline (bypasses Groq)
# ---------------------------------------------------------------------------

def fetch_official_announcements(seen: dict) -> list:
    """שולף הודעות רשמיות מהאתר הרשמי ומחזיר רק חדשות שלא נשלחו עדיין."""
    feed_url = "https://www.maccabi-haifa.co.il/feed/"
    new_items = []
    try:
        result = feedparser.parse(feed_url)
        if result.get("bozo") and not result.get("entries"):
            logging.warning("[OFFICIAL-site] Feed parse error.")
            return []

        cutoff = datetime.now(timezone.utc) - timedelta(hours=MAX_ARTICLE_AGE_HOURS)
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

            if not title:
                continue

            # בדוק אם הכותרת/תקציר מכילים מילת מפתח רלוונטית
            text_lower = (title + " " + summary).lower()
            if not any(kw.lower() in text_lower for kw in OFFICIAL_KEYWORDS):
                continue

            h = hashlib.md5(f"official-{link}".encode()).hexdigest()
            if h in seen:
                continue

            new_items.append({
                "hash": h,
                "title": title,
                "link": link,
                "summary": summary[:300],
                "published": published,
            })
            logging.info(f"[OFFICIAL-site] New announcement: {title[:80]}")

    except Exception as e:
        logging.warning(f"[OFFICIAL-site] Fetch error: {e}")

    return new_items


def format_official_message(item: dict) -> str:
    return (
        f"{RTL}📢 *הודעה רשמית — מכבי חיפה*\n\n"
        f"{RTL}*{item['title']}*\n\n"
        f"{RTL}{item['summary'][:250]}\n\n"
        f"{RTL}🔗 [קרא באתר הרשמי]({item['link']})"
    )


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

    new_count = 0
    had_urgent = False

    # Official site — direct pipeline (no Groq needed)
    official_items = fetch_official_announcements(seen)
    for oi in official_items:
        msg = format_official_message(oi)
        if send_telegram(bot_token, chat_id, msg):
            seen[oi["hash"]] = datetime.now(timezone.utc).isoformat()
            had_urgent = True
            new_count += 1
            logging.info(f"[OFFICIAL] Sent: {oi['title'][:60]}")
        time.sleep(1)

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

    for item in filtered:
        player = item.get("player")
        transfer_type = item.get("type", "")
        title = item.get("title", "")
        urgency = item.get("urgency", 1)

        if urgency < MIN_URGENCY:
            logging.info(f"Urgency {urgency} below threshold, skipping: {title[:60]}")
            continue

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
