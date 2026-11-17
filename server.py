import requests, re, html, time, os
from flask import Flask, render_template_string, make_response, jsonify, request
from datetime import datetime, timezone
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

app = Flask(__name__)

SOURCES = [
    "https://news.google.com/rss/search?q=site%3Aotcmarkets.com%20stock%20news&hl=en-US&gl=US&ceid=US:en",
    "https://www.bing.com/news/search?q=site%3Aotcmarkets.com&format=rss",
]

STRONG = {
    "fda approval": 30,
    "fda": 20,
    "merger": 28,
    "acquisition": 28,
    "acquired": 25,
    "earnings": 18,
    "contract": 20,
    "partnership": 18,
    "nasdaq uplisting": 30,
    "uplist": 25,
    "clinical trial": 22,
    "phase 3": 25,
    "phase 2": 18,
    "breakthrough": 25,
    "patent": 15,
    "launch": 12,
    "expansion": 12,
    "dividend": 15,
    "buyback": 18,
    "guidance raised": 25,
    "beat estimates": 20,
    "bankruptcy": -20,
    "delisting": -20,
    "reverse split": -15,
    "dilution": -10,
    "annual revenue": 30,
    "record annual revenue": 35,
    "revenue exceeds": 30,
    "revenue exceeds market cap": 35,
    "undervalued": 28,
    "market cap": 12,
    "low market cap": 25,
    "revenue growth": 25,
    "profitable": 25,
    "net profit": 25,
    "net income": 22,
    "positive cash flow": 28,
    "revenue of $": 20,
    "revenue increased": 22,
    "revenue surged": 28,
    "revenue up": 20,
    "sales growth": 22,
    "record sales": 25,
    "otcqx": 12,
    "otcqb": 10,
    "revenue": 15,
    "record revenue": 25,
}

def hebrew_summary(title, desc):
    text = (title + " " + desc).lower()
    if "revenue exceeds" in text:
        return "REV_EXCEEDS"
    if "annual revenue" in text:
        return "ANNUAL_REV"
    if "undervalued" in text:
        return "UNDERVALUED"
    if "positive cash flow" in text:
        return "CASH_FLOW"
    if "profitable" in text:
        return "PROFITABLE"
    if "net profit" in text:
        return "PROFITABLE"
    if "revenue growth" in text:
        return "REV_GROWTH"
    if "revenue surged" in text:
        return "REV_GROWTH"
    if "fda approval" in text:
        return "FDA_APPROVAL"
    if "uplist" in text:
        return "UPLIST"
    if "merger" in text:
        return "MERGER"
    if "acquisition" in text:
        return "MERGER"
    if "phase 3" in text:
        return "PHASE3"
    if "clinical trial" in text:
        return "TRIAL"
    if "record revenue" in text:
        return "RECORD_REV"
    if "contract" in text:
        return "CONTRACT"
    if "partnership" in text:
        return "PARTNERSHIP"
    if "dividend" in text:
        return "DIVIDEND"
    if "bankruptcy" in text:
        return "BANKRUPTCY"
    if "reverse split" in text:
        return "NEGATIVE"
    if "delisting" in text:
        return "NEGATIVE"
    if "breakthrough" in text:
        return "BREAKTHROUGH"
    if "patent" in text:
        return "PATENT"
    if "buyback" in text:
        return "BUYBACK"
    return "GENERAL"

SUMMARY_HE = {
    "REV_EXCEEDS": "מחזור גבוה מהשווי - החברה מכניסה יותר ממה שהיא שווה",
    "ANNUAL_REV": "מחזור שנתי חזק - תבדוק אם המחזור קרוב לשווי השוק",
    "UNDERVALUED": "חברה מתומחרת בחסר - שווי נמוך ממה שהיא שווה",
    "CASH_FLOW": "תזרים מזומנים חיובי - החברה באמת מכניסה כסף",
    "PROFITABLE": "חברה רווחית - נשארת עם רווח בסוף",
    "REV_GROWTH": "צמיחה בהכנסות",
    "FDA_APPROVAL": "אישור FDA - הטריגר הכי חזק שיש",
    "UPLIST": "מעבר לנאסדק",
    "MERGER": "מיזוג / רכישה",
    "PHASE3": "תוצאות שלב 3",
    "TRIAL": "תוצאות ניסוי קליני",
    "RECORD_REV": "הכנסות שיא",
    "CONTRACT": "חוזה חדש - כסף אמיתי שנכנס",
    "PARTNERSHIP": "שותפות אסטרטגית",
    "DIVIDEND": "דיבידנד",
    "BANKRUPTCY": "סכנת פשיטת רגל",
    "NEGATIVE": "איתות שלילי",
    "BREAKTHROUGH": "פריצת דרך",
    "PATENT": "פטנט חדש",
    "BUYBACK": "החברה קונה את המניות של עצמה",
    "GENERAL": "חדשה עם עניין בשוק",
}

def get_score(title, desc):
    text = (title + " " + desc).lower()
    score = 30
    for word, pts in STRONG.items():
        if word in text:
            score += pts
    has_rev = "revenue" in text
    has_val = "market cap" in text
    has_under = "undervalued" in text
    if has_rev and (has_val or has_under):
        score += 15
    if score < 1:
        score = 1
    if score > 100:
        score = 100
    return score

def get_ticker(title, desc):
    text = title + " " + desc
    m = re.findall(r'\b[A-Z]{2,5}\b', text)
    bad = ["FDA", "CEO", "OTC", "USA", "US", "SEC", "THE", "AND", "FOR"]
    for t in m:
        if t not in bad:
            return t
    return "OTC"

def clean_text(s):
    if not s:
        return ""
    s = re.sub(r'<[^>]+>', '', s)
    s = html.unescape(s)
    return s[:200]

def parse_date(item):
    for tag in ["pubDate", "published", "updated", "date"]:
        val = item.findtext(tag)
        if val:
            try:
                dt = parsedate_to_datetime(val)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except:
                pass
    for child in item:
        if child.tag.endswith('published'):
            try:
                dt = parsedate_to_datetime(child.text)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except:
                pass
        if child.tag.endswith('updated'):
            try:
                dt = parsedate_to_datetime(child.text)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except:
                pass
    return None

def fetch_tickwatch_real():
    out = []
    try:
        r = requests.get(
            "https://tickwatch.online/",
            timeout=12,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        if r.status_code != 200:
            return []
        txt = r.text
        links = re.findall(
            r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
            txt,
            re.S
        )
        seen = set()
        for href, inner in links:
            title = re.sub(r'<[^>]+>', '', inner).strip()
            title = html.unescape(title)
            if len(title) < 20:
                continue
            if len(title) > 180:
                continue
            if href.startswith("#"):
                continue
            if href in seen:
                continue
            low = href.lower()
            if "about" in low:
                continue
            if "contact" in low:
                continue
            if "privacy" in low:
                continue
            if "login" in low:
                continue
            if "signup" in low:
                continue
            if href.startswith("/"):
                link = "https://tickwatch.online" + href
            elif "tickwatch.online" in href:
                link = href
            else:
                continue
            if link in seen:
                continue
            seen.add(link)
            ticker = get_ticker(title, "")
            score = get_score(title, "")
            code = hebrew_summary(title, title)
            summary = SUMMARY_HE.get(code, "GENERAL")
            out.append({
                "ticker": ticker,
                "title": title,
                "desc": title,
                "summary": summary,
                "link": link,
                "score": score,
                "time": datetime.now().strftime("%H:%M"),
                "age": "TickWatch"
            })
            if len(out) >= 10:
                break
        return out
    except Exception as e:
        print("tickwatch err", e)
        return []

def fetch_otcmarkets_real():
    out = []
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(
            "https://blog.otcmarkets.com/feed/",
            timeout=12,
            headers=headers
        )
        if r.status_code == 200 and r.content:
            root = ET.fromstring(r.content)
            items = root.findall(".//item")
            for item in items[:15]:
                title = item.findtext("title") or ""
                link = item.findtext("link") or "#"
                desc = item.findtext("description") or ""
                if not title:
                    continue
                if link == "#":
                    continue
                title = html.unescape(title.strip())
                desc = clean_text(desc)
                score = get_score(title, desc)
                pub = parse_date(item)
                t = pub.strftime("%H:%M") if pub else datetime.now().strftime("%H:%M")
                code = hebrew_summary(title, desc)
                summary = SUMMARY_HE.get(code, "GENERAL")
                out.append({
                    "ticker": get_ticker(title, desc),
                    "title": title,
                    "desc": desc,
                    "summary": summary,
                    "link": link,
                    "score": score,
                    "time": t,
                    "age": "OTC Markets Blog"
                })
    except Exception as e:
        print("otc blog err", e)
    if len(out) < 5:
        try:
            api_url = "https://www.otcmarkets.com/api/news?sort=date&page=1&pageSize=20"
            r = requests.get(api_url, timeout=12, headers=headers)
            if r.status_code == 200 and r.text:
                txt = r.text
                titles = re.findall(
                    r'"(?:title|headline)"\s*:\s*"([^"]{25,200})"',
                    txt
                )
                links = re.findall(
                    r'"(?:url|link|href)"\s*:\s*"([^"]+)"',
                    txt
                )
                for i, t in enumerate(titles[:10]):
                    title = html.unescape(t.strip())
                    if i < len(links):
                        link = links[i]
                    else:
                        link = "https://www.otcmarkets.com/news"
                    if link.startswith("/"):
                        link = "https://www.otcmarkets.com" + link
                    score = get_score(title, title)
                    dup = False
                    for o in out
