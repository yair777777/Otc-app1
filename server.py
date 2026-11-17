import requests, re, html, time, os
from flask import Flask, render_template_string, make_response, jsonify, request
from datetime import datetime, timezone
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

app = Flask(__name__)

SOURCES = [
    "https://www.otcmarkets.com/news/rss",
    "https://www.globenewswire.com/RssFeed/subjectcode/13/OTC%20Markets/feed.xml",
    "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&type=8-K&dateb=&owner=include&count=40&output=atom",
    "https://www.businesswire.com/rss/home/",
    "https://www.stocktitan.net/rss/",
]

BACKUP_SOURCES = [
    "https://news.google.com/rss/search?q=OTC+stocks&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=penny+stocks&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=small+cap+stocks+earnings&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=OTC+Markets+press+release&hl=en-US&gl=US&ceid=US:en",
]

STRONG = {
    "fda approval": 30, "fda": 20, "merger": 28, "acquisition": 28,
    "acquired": 25, "earnings": 18, "revenue": 15, "record revenue": 25,
    "contract": 20, "partnership": 18, "nasdaq uplisting": 30, "uplist": 25,
    "clinical trial": 22, "phase 3": 25, "phase 2": 18, "breakthrough": 25,
    "patent": 15, "launch": 12, "expansion": 12, "dividend": 15,
    "buyback": 18, "guidance raised": 25, "beat estimates": 20,
    "bankruptcy": -20, "delisting": -20, "reverse split": -15, "dilution": -10,
    "annual revenue": 18, "full year revenue": 20, "full-year revenue": 20
}

DEBUG_LOG = {"last_fetch": "לא בוצעה סריקה עדיין", "sources": [], "total": 0}

def _parse_money_num(num_str, unit):
    try:
        v = float(num_str.replace(",", ""))
    except:
        return None
    u = (unit or "").lower()
    if "billion" in u or u == "b":
        v *= 1000
    return v

def _find_money_near(text, keywords):
    for kw in keywords:
        idx = text.find(kw)
        while idx != -1:
            window = text[idx:idx+120]
            m = re.search(r'\$\s*([\d,]+\.?\d*)\s*(billion|million|b|m)?', window)
            if m:
                val = _parse_money_num(m.group(1), m.group(2) or "m")
                if val:
                    return val
            idx = text.find(kw, idx+1)
    return None

def revenue_vs_cap(title, desc):
    text = (title + " " + desc).lower()
    rev = _find_money_near(text, ["annual revenue", "full year revenue", "full-year revenue", "revenue of", "revenues of", "revenue was", "total revenue"])
    cap = _find_money_near(text, ["market cap", "market capitalization", "market value"])
    if rev is None:
        rev = _find_money_near(text, ["revenue"])
    if cap is None:
        cap = _find_money_near(text, ["market cap"])
    if rev and cap and cap > 0:
        return rev, cap
    return None, None

def hebrew_summary(title, desc):
    text = (title + " " + desc).lower()
    rev, cap = revenue_vs_cap(title, desc)
    if rev and cap:
        ratio = rev / cap
        if ratio >= 1:
            return f"💰 מחזור שנתי חיובי ביחס לשווי - הכנסה שנתית של כ-${rev:.0f}M מול שווי שוק של כ-${cap:.0f}M. החברה מכניסה בשנה יותר ממה שהיא שווה בבורסה."
        if ratio >= 0.5:
            return f"💰 מחזור שנתי חזק ביחס לשווי - הכנסה שנתית של כ-${rev:.0f}M מול שווי שוק של כ-${cap:.0f}M. יחס חזק מאוד ל-OTC."
    if "fda approval" in text:
        return "🔥 אישור FDA - הטריגר הכי חזק שיש."
    if "nasdaq uplisting" in text or "uplist" in text:
        return "🔥 מעבר לנאסד״ק - עובר מ-OTC לבורסה הגדולה."
    if "merger" in text or "acquisition" in text or "acquired" in text:
        return "🔥 מיזוג / רכישה - חברה גדולה קונה אותה."
    if "phase 3" in text:
        return "💊 תוצאות שלב 3 - השלב האחרון לפני אישור FDA."
    if "clinical trial" in text or "phase 2" in text:
        return "💊 תוצאות ניסוי קליני - אם התרופה עובדת, החברה שווה הרבה יותר."
    if "record revenue" in text:
        return "💰 הכנסות שיא - החברה מכניסה יותר כסף מאי פעם."
    if "guidance raised" in text or "beat estimates" in text:
        return "💰 עקפה את התחזיות והעלתה ציפיות."
    if "contract" in text:
        return "📝 חוזה חדש - כסף אמיתי שנכנס לחברה."
    if "partnership" in text:
        return "🤝 שותפות אסטרטגית - חברה גדולה שמה את השם שלה על הקטנה."
    if "earnings" in text or "revenue" in text:
        return "📊 דוחות כספיים - רואים אם החברה באמת מרוויחה."
    if "buyback" in text:
        return "💵 החברה קונה את המניות של עצמה."
    if "patent" in text:
        return "💡 פטנט חדש - הגנה על המוצר לשנים."
    if "breakthrough" in text:
        return "🚀 פריצת דרך."
    if "dividend" in text:
        return "💵 דיבידנד - החברה מחלקת כסף לבעלי המניות."
    if "bankruptcy" in text:
        return "⚠️ סכנת פשיטת רגל."
    if "reverse split" in text or "delisting" in text:
        return "⚠️ איתות שלילי - פיצול הפוך / מחיקה מהמסחר."
    if "launch" in text:
        return "🚀 השקת מוצר חדש."
    return "👀 חדשה עם עניין בשוק - מוצג כי צריך תמיד 10, גם אם אין טריגר חזק כרגע."

def get_score(title, desc):
    text = (title + " " + desc).lower()
    score = 30
    for word, pts in STRONG.items():
        if word in text:
            score += pts
    rev, cap = revenue_vs_cap(title, desc)
    if rev and cap and cap > 0:
        ratio = rev / cap
        if ratio >= 1:
            score += 30
        elif ratio >= 0.5:
            score += 20
        elif ratio >= 0.3:
            score += 10
    return max(1, min(100, score))

# --- תיקון 1: חילוץ טיקר + שם חברה אמיתי ---
def get_ticker(title, desc, link=""):
    text = (title + " " + desc + " " + link)
    # 1. הפורמט של StockTitan ו-GlobeNewswire: (NASDAQ: AAPL) / (OTCQB: XYZ) / (NYSE: MSFT)
    m = re.search(r'\((?:NASDAQ|NYSE|NYSE American|OTCQB|OTCQX|OTCQB|OTC|AMEX|NASDAQ Capital Market)[\s:]*([A-Z]{1,5})\)', text)
    if m:
        return m.group(1)
    # 2. NASDAQ: AAPL בלי סוגריים
    m = re.search(r'\b(?:NASDAQ|NYSE|OTCQB|OTCQX|OTC)[:\s]+([A-Z]{1,5})\b', text)
    if m:
        return m.group(1)
    # 3. Ticker: AAPL
    m = re.search(r'\bTicker[:\s]+([A-Z]{1,5})\b', text, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    # 4. מילה באותיות גדולות שהיא לא מילה רגילה - לא THE / AND / FDA
    blacklist = {"FDA","CEO","OTC","USA","US","SEC","THE","AND","FOR","WITH","FROM","NEWS","INC","LTD","CORP","LLC","PLC","FDA","NEW","STOCK","MARKET","SHARES","REPORTS","ANNOUNCES","TODAY","FIRST","SECOND"}
    for t in re.findall(r'\b[A-Z]{2,5}\b', text):
        if t not in blacklist:
            return t
    return "OTC"

def get_company(title):
    if not title:
        return ""
    # "Apple Inc. (NASDAQ: AAPL) Reports Earnings" -> "Apple Inc."
    if " (" in title:
        name = title.split(" (")[0].strip()
        if len(name) >= 3:
            return name
    # "Apple Inc. - Reports..." -> "Apple Inc."
    if " - " in title:
        name = title.split(" - ")[0].strip()
        if 3 <= len(name) <= 70:
            return name
    # "Apple: Reports..." -> "Apple"
    if ":" in title:
        name = title.split(":")[0].strip()
        if 3 <= len(name) <= 70 and " " in name:
            return name
    return ""

def clean_text(s):
    if not s: return ""
    s = re.sub(r'<[^>]+>', '', s)
    return html.unescape(s)[:200]

def _get_child_text(item, names):
    for child in item:
        tag = child.tag.split('}')[-1].lower()
        if tag in names and child.text:
            return child.text.strip()
        if tag == 'link' and child.get('href'):
            return child.get('href')
    return ""

def parse_date(item):
    raw = _get_child_text(item, ["pubdate", "published", "updated", "date"])
    if raw:
        try:
            dt = parsedate_to_datetime(raw)
            if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except:
            try:
                dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except: pass
    return None

def deep_check(ticker, base_score, title, desc):
    rev, cap = revenue_vs_cap(title, desc)
    is_interesting = base_score >= 70 or (rev and cap and cap > 0 and rev / cap >= 0.5)
    if not is_interesting or not ticker or ticker == "OTC":
        return base_score, ""
    try:
        url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"
        r = requests.get(url, timeout=4, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200 or not r.content:
            return base_score, ""
        root = ET.fromstring(r.content)
        items = root.findall(".//item")
        if not items:
            return base_score, ""
        bonus = 0
        found = 0
        found_words = []
        for item in items[:5]:
            t2 = (item.findtext("title") or "") + " " + (item.findtext("description") or "")
            t2_low = t2.lower()
            for word, pts in STRONG.items():
                if word in t2_low and pts > 0 and word not in found_words:
                    found_words.append(word)
                    found += 1
                    bonus += 5
                    break
        if found == 0:
            return base_score, ""
        new_score = max(1, min(100, base_score + bonus))
        note = f"🔍 בדיקה עמוקה על {ticker}: נמצאו עוד {found} חדשות חיוביות על המניה עצמה - הציון עלה מ-{base_score} ל-{new_score}."
        return new_score, note
    except:
        return base_score, ""

# --- תיקון 2: StockTitan - חלק מהאתר, לעולם לא נכשל ---
# האתר שלהם JS ולא נותן RSS ישיר, אז מביאים דרך Google News site:stocktitan.net
# זה מחזיר כותרות אמיתיות עם לינקים ל-stocktitan.net
def fetch_stocktitan(url, all_news):
    src_info = {"url": "stocktitan", "status": 0, "found": 0, "kept": 0, "error": "", "backup": False}
    try:
        r = requests.get("https://news.google.com/rss/search?q=site:stocktitan.net&hl
