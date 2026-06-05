# -*- coding: utf-8 -*-
"""
ניתוח סטטיסטי - הגרלות לוטו 3 שנים אחורה
שולף נתונים מ-paisAPI + אתר פייס הרשמי
"""
import requests, json, time, collections
from datetime import datetime

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# ─── שליפה מ-paisAPI ───────────────────────────────────────
def fetch_from_api(start_id, end_id):
    url = f"https://paisapi.azurewebsites.net/lotto/byID/{start_id}/{end_id}"
    try:
        r = requests.get(url, timeout=30)
        data = r.json()
        draws = []
        for d in data:
            nums = sorted(d.get("winNumbers", []))
            strong = d.get("strongNumber", 0)
            date = d.get("date", "")[:10]
            did = d.get("_id", d.get("id", 0))
            if nums and len(nums) == 6:
                draws.append({"id": did, "date": date, "numbers": nums, "strong": strong})
        print(f"  API: שלפתי {len(draws)} הגרלות ({start_id}-{end_id})")
        return draws
    except Exception as e:
        print(f"  API error: {e}")
        return []

# ─── שליפה מאתר פייס הרשמי ──────────────────────────────────
def fetch_from_pais(draw_id):
    url = f"https://www.pais.co.il/Lotto/CurrentLotto.aspx?lotteryId={draw_id}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(r.text, "html.parser")

        # חיפוש מספרים בעיצוב האתר
        numbers = []
        strong = None

        # כדורים ראשיים
        balls = soup.select(".lottery-result .ball, .lotto-ball, .number-ball, [class*='ball']")
        if not balls:
            # ניסיון חלופי
            balls = soup.find_all(class_=lambda c: c and "ball" in c.lower())

        for b in balls:
            try:
                n = int(b.get_text(strip=True))
                if 1 <= n <= 37:
                    numbers.append(n)
            except:
                pass

        # חיפוש מספר חזק
        strong_el = soup.find(class_=lambda c: c and ("strong" in c.lower() or "חזק" in str(c)))
        if strong_el:
            try:
                strong = int(strong_el.get_text(strip=True))
            except:
                pass

        if len(numbers) >= 6:
            return {
                "id": draw_id,
                "date": "",
                "numbers": sorted(numbers[:6]),
                "strong": strong or 0
            }
    except Exception as e:
        pass
    return None

# ─── שליפה ידנית - נתונים ידועים ───────────────────────────
# נתונים שאספנו ידנית מה-WebFetch
KNOWN_DRAWS = [
    {"id": 3900, "date": "2026-02-19", "numbers": [7, 9, 25, 26, 35, 36], "strong": 3},
    {"id": 3927, "date": "2026-05-19", "numbers": [4, 10, 18, 21, 32, 33], "strong": 2},
]

# ─── ניתוח סטטיסטי ─────────────────────────────────────────
def analyze(draws):
    print(f"\n{'='*55}")
    print(f"  סה\"כ הגרלות לניתוח: {len(draws)}")
    print(f"{'='*55}")

    freq = collections.Counter()
    strong_freq = collections.Counter()
    pairs = collections.Counter()
    gap = {i: 0 for i in range(1, 38)}   # כמה הגרלות מאז עלה לאחרונה
    last_seen = {}

    for i, d in enumerate(draws):
        for n in d["numbers"]:
            freq[n] += 1
            last_seen[n] = i
        if d["strong"]:
            strong_freq[d["strong"]] += 1
        nums = sorted(d["numbers"])
        for j in range(len(nums)):
            for k in range(j+1, len(nums)):
                pairs[(nums[j], nums[k])] += 1

    total = len(draws)

    # חישוב "גיל" כל מספר — כמה הגרלות עברו מאז עלה
    for n in range(1, 38):
        if n in last_seen:
            gap[n] = total - 1 - last_seen[n]
        else:
            gap[n] = total

    print("\n📊 תדירות מספרים (1-37) — אחוז הופעה:")
    for n in range(1, 38):
        pct = freq[n] / total * 100
        bar = "█" * int(pct * 1.2)
        print(f"  {n:2d}: {pct:5.1f}%  {bar}")

    print("\n🔥 TOP 10 מספרים חמים (הכי הרבה הופעות):")
    for n, cnt in freq.most_common(10):
        print(f"  {n:2d} — {cnt} פעמים ({cnt/total*100:.1f}%)")

    print("\n❄️  TOP 10 מספרים קרים (הכי מעט הופעות):")
    for n, cnt in freq.most_common()[:-11:-1]:
        print(f"  {n:2d} — {cnt} פעמים ({cnt/total*100:.1f}%) | {gap[n]} הגרלות מאז")

    print("\n⏰ TOP 10 מספרים שלא עלו הכי הרבה זמן (overdue):")
    overdue = sorted(gap.items(), key=lambda x: x[1], reverse=True)[:10]
    for n, g in overdue:
        print(f"  {n:2d} — לא עלה {g} הגרלות (נראה {freq[n]} פעמים סה\"כ)")

    print("\n💪 TOP 5 זוגות שעולים יחד הכי הרבה:")
    for (a, b), cnt in pairs.most_common(5):
        print(f"  {a}+{b} — {cnt} פעמים")

    print("\n🎯 מספר חזק — תדירות:")
    for n, cnt in strong_freq.most_common():
        print(f"  {n}: {cnt} פעמים")

    return freq, strong_freq, gap

# ─── המלצת טופס ────────────────────────────────────────────
def recommend(freq, strong_freq, gap, total):
    print(f"\n{'='*55}")
    print("  🎰 המלצת טופס להגרלה מחר")
    print(f"{'='*55}")
    print("  (אזהרה: לוטו מבוסס מזל — אין הבטחת זכייה!)\n")

    # אסטרטגיה: 2 חמים + 2 קרים + 2 overdue
    hot = [n for n, _ in freq.most_common(12)]
    cold = [n for n, _ in freq.most_common()[:-13:-1]]
    overdue = sorted(gap.items(), key=lambda x: x[1], reverse=True)
    overdue_nums = [n for n, g in overdue if g > 5][:12]

    import random
    random.seed(42)

    picked = set()
    # 2 חמים
    for n in hot:
        if n not in picked and len(picked) < 2:
            picked.add(n)
    # 2 קרים
    for n in cold:
        if n not in picked and len(picked) < 4:
            picked.add(n)
    # 2 overdue
    for n in overdue_nums:
        if n not in picked and len(picked) < 6:
            picked.add(n)
    # השלמה אם צריך
    while len(picked) < 6:
        n = random.randint(1, 37)
        picked.add(n)

    nums = sorted(picked)
    strong_pick = strong_freq.most_common(1)[0][0] if strong_freq else 7

    print(f"  📋 טופס מוצע:")
    print(f"  מספרים: {', '.join(str(n) for n in nums)}")
    print(f"  מספר חזק: {strong_pick}")
    print()
    print(f"  🔥 חמים:   {', '.join(str(n) for n, _ in freq.most_common(3))}")
    print(f"  ❄️  קרים:   {', '.join(str(n) for n, _ in freq.most_common()[:-4:-1])}")
    print(f"  ⏰ Overdue: {', '.join(str(n) for n, _ in sorted(gap.items(), key=lambda x: x[1], reverse=True)[:3])}")

# ─── הרצה ראשית ────────────────────────────────────────────
def main():
    print("🔍 שולף נתוני הגרלות...")

    # שליפה מ-API (זמין עד ~הגרלה 3716)
    api_draws = fetch_from_api(3614, 3800)

    # נתונים ידועים שאספנו
    all_draws = api_draws[:]
    existing_ids = {d["id"] for d in all_draws}
    for d in KNOWN_DRAWS:
        if d["id"] not in existing_ids:
            all_draws.append(d)

    # מיון לפי ID
    all_draws.sort(key=lambda x: x["id"])

    print(f"\n📦 סה\"כ הגרלות שנאספו: {len(all_draws)}")
    if all_draws:
        print(f"   טווח: {all_draws[0]['id']} ({all_draws[0]['date']}) עד {all_draws[-1]['id']} ({all_draws[-1]['date']})")

    # ניתוח
    freq, strong_freq, gap = analyze(all_draws)
    recommend(freq, strong_freq, gap, len(all_draws))

    # שמירת נתונים ל-JSON
    with open("draws_data.json", "w", encoding="utf-8") as f:
        json.dump(all_draws, f, ensure_ascii=False, indent=2)
    print(f"\n💾 נתונים נשמרו ל-draws_data.json")

if __name__ == "__main__":
    main()
