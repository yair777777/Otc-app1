import requests, re, html, time, os
from flask import Flask, render_template_string, make_response, jsonify, request
from datetime import datetime, timezone
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

app = Flask(__name__)

SOURCES = [
    "https://www.otcmarkets.com/news/rss",
    "https://www.globenewswire.com/RssFeed/subjectcode/13/OTC%20Markets/feed.xml",
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
            return f"💰 מחזור שנתי חיובי ביחס לשווי - הכנסה שנתית של כ-${rev:.0f}M מול שווי שוק של כ-${cap:.0f}M. החברה מכניסה בשנה יותר ממה שהיא שווה בבורסה, זה אומר שהמניה זולה ביחס למה שהיא באמת מכניסה."
        if ratio >= 0.5:
            return f"💰 מחזור שנתי חזק ביחס לשווי - הכנסה שנתית של כ-${rev:.0f}M מול שווי שוק של כ-${cap:.0f}M. החברה מכניסה בשנה יותר מחצי ממה שהיא שווה, זה יחס חזק מאוד ל-OTC."
    if "fda approval" in text:
        return "🔥 אישור FDA - הטריגר הכי חזק שיש. החברה יכולה עכשיו למכור את המוצר, זה מה שמביא בדרך כלל את הקפיצה הכי גדולה."
    if "nasdaq uplisting" in text or "uplist" in text:
        return "🔥 מעבר לנאסד״ק - עובר מ-OTC לבורסה הגדולה. זה מכניס קרנות גדולות שלא יכלו לקנות לפני."
    if "merger" in text or "acquisition" in text or "acquired" in text:
        return "🔥 מיזוג / רכישה - חברה גדולה קונה אותה, בדרך כלל במחיר גבוה ממחיר השוק."
    if "phase 3" in text:
        return "💊 תוצאות שלב 3 - השלב האחרון לפני אישור FDA. אם התוצאות טובות, זה כמעט אישור."
    if "clinical trial" in text or "phase 2" in text:
        return "💊 תוצאות ניסוי קליני - אם התרופה עובדת, החברה שווה הרבה יותר."
    if "record revenue" in text:
        return "💰 הכנסות שיא - החברה מכניסה יותר כסף מאי פעם."
    if "guidance raised" in text or "beat estimates" in text:
        return "💰 עקפה את התחזיות והעלתה ציפיות."
    if "contract" in text:
        return "📝 חוזה חדש - כסף אמיתי שנכנס לחברה, לא רק דיבורים."
    if "partnership" in text:
        return "🤝 שותפות אסטרטגית - חברה גדולה שמה את השם שלה על הקטנה."
    if "earnings" in text or "revenue" in text:
        return "📊 דוחות כספיים - זה הרגע שבו רואים אם החברה באמת מרוויחה."
    if "buyback" in text:
        return "💵 החברה קונה את המניות של עצמה - היא מאמינה שהמניה זולה מדי."
    if "patent" in text:
        return "💡 פטנט חדש - הגנה על המוצר לשנים."
    if "breakthrough" in text:
        return "🚀 פריצת דרך - משהו חדש שהשוק לא ציפה לו."
    if "dividend" in text:
        return "💵 דיבידנד - החברה מחלקת כסף לבעלי המניות."
    if "bankruptcy" in text:
        return "⚠️ סכנת פשיטת רגל - ציון נמוך בכוונה."
    if "reverse split" in text or "delisting" in text:
        return "⚠️ איתות שלילי - פיצול הפוך / מחיקה מהמסחר."
    if "launch" in text:
        return "🚀 השקת מוצר חדש - מתחיל להכניס כסף מהמוצר."
    return "👀 חדשה עם עניין בשוק - אין טריגר אחד ברור, אבל יש תנועה ותשומת לב סביב המניה."

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

def get_ticker(title, desc):
    text = title + " " + desc
    m = re.findall(r'\b[A-Z]{2,5}\b', text)
    for t in m:
        if t not in ["FDA", "CEO", "OTC", "USA", "US", "SEC", "THE", "AND", "FOR"]:
            return t
    return "OTC"

def clean_text(s):
    if not s: return ""
    s = re.sub(r'<[^>]+>', '', s)
    return html.unescape(s)[:200]

def parse_date(item):
    for tag in ["pubDate", "published", "updated", "date"]:
        val = item.findtext(tag)
        if val:
            try:
                dt = parsedate_to_datetime(val)
                if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except: pass
    for child in item:
        if child.tag.endswith('published') or child.tag.endswith('updated'):
            try:
                if not child.text: continue
                dt = parsedate_to_datetime(child.text)
                if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except: pass
    return None

def deep_check(ticker, base_score, title, desc):
    # בדיקה עמוקה - רק אם החדשה הראשונה הייתה מעניינת
    rev, cap = revenue_vs_cap(title, desc)
    is_interesting = base_score >= 70 or (rev and cap and cap > 0 and rev / cap >= 0.5)
    if not is_interesting or not ticker or ticker == "OTC":
        return base_score, ""
    try:
        url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"
        r = requests.get(url, timeout=5, headers={"User-Agent": "Mozilla/5.0", "Cache-Control": "no-cache"})
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

def fetch_all():
    all_news = []
    now = datetime.now(timezone.utc)
    for url in SOURCES:
        try:
            r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0", "Cache-Control": "no-cache"})
            if r.status_code != 200 or not r.content: continue
            root = ET.fromstring(r.content)
            items = root.findall(".//item")
            if not items:
                items = [e for e in root.iter() if e.tag.endswith('entry')]
            for item in items[:30]:
                title = item.findtext("title") or ""
                link = item.findtext("link") or "#"
                desc = item.findtext("description") or item.findtext("summary") or ""
                if link == "#" or not link:
                    for child in item:
                        if child.tag.endswith('link') and child.get('href'):
                            link = child.get('href'); break
                if not title: continue
                pub = parse_date(item)
                if pub:
                    age_hours = (now - pub).total_seconds() / 3600
                    if age_hours > 48: continue
                else:
                    age_hours = 999
                title = html.unescape(title.strip())
                desc = clean_text(desc)
                score = get_score(title, desc)
                ticker = get_ticker(title, desc)
                all_news.append({
                    "ticker": ticker,
                    "title": title, "desc": desc,
                    "summary": hebrew_summary(title, desc),
                    "link": link if link else "#",
                    "score": score,
                    "time": pub.strftime("%H:%M") if pub else datetime.now().strftime("%H:%M"),
                    "age": f"{int(age_hours)} שעות" if age_hours < 48 else "ישן",
                    "deep": ""
                })
        except Exception as e:
            print("err", url, e); continue
    # מיון ראשוני כדי לבדוק לעומק רק את המעניינות ביותר
    all_news = sorted(all_news, key=lambda x: x["score"], reverse=True)
    # בדיקה עמוקה - רק על 5 הראשונות הכי מעניינות, כדי לא להאט את הסריקה
    deep_count = 0
    for n in all_news:
        if deep_count >= 5:
            break
        rev, cap = revenue_vs_cap(n["title"], n["desc"])
        is_interesting = n["score"] >= 70 or (rev and cap and cap > 0 and rev / cap >= 0.5)
        if not is_interesting:
            continue
        new_score, note = deep_check(n["ticker"], n["score"], n["title"], n["desc"])
        if note:
            n["score"] = new_score
            n["deep"] = note
            deep_count += 1
    # מיון סופי לפי ציון בלבד - אחרי הבדיקה העמוקה
    all_news = sorted(all_news, key=lambda x: x["score"], reverse=True)
    return all_news[:10]

CACHE = {"data": [], "time": 0, "scans": 0}

def refresh_cache(force=False):
    if force:
        CACHE["time"] = 0
    if force or time.time() - CACHE["time"] > 120 or not CACHE["data"]:
        data = fetch_all()
        CACHE["time"] = time.time()
        CACHE["scans"] += 1
        if data:
            CACHE["data"] = data
    return CACHE["data"]

@app.route("/api/news")
def api_news():
    force = request.args.get("force") == "1"
    data = refresh_cache(force=force)
    resp = jsonify({"news": data, "last_scan": datetime.now().strftime("%H:%M:%S"), "scans": CACHE["scans"], "server_time": time.time()})
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp

@app.route("/")
def home():
    force = request.args.get("refresh") == "1"
    news = refresh_cache(force=force)
    html_out = render_template_string(HTML, news=news, updated=datetime.now().strftime("%H:%M:%S"))
    resp = make_response(html_out)
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp

HTML = """
<!DOCTYPE html><html dir="rtl" lang="he"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>OTC Radar</title>
<style>
body{background:#0a0a0a;color:#fff;font-family:Arial;padding:15px}
h1{text-align:center;margin:5px} .sub{text-align:center;color:#aaa;margin-bottom:8px}
.live{background:#1a2a1a;border:1px solid #00c853;border-radius:10px;padding:10px;text-align:center;margin-bottom:12px;font-size:14px}
.dot{display:inline-block;width:10px;height:10px;background:#00ff00;border-radius:50%;animation:blink 1s infinite}
@keyframes blink{0%{opacity:1}50%{opacity:0.2}100%{opacity:1}}
.card{background:#1a1a1a;border-radius:12px;padding:14px;margin-bottom:12px;border-right:5px solid #00c853}
.card.top{border-right-color:#ff9800}
.score{float:left;background:#00c853;color:#000;font-weight:bold;padding:5px 10px;border-radius:20px;font-size:18px}
.ticker{color:#00e676;font-weight:bold;font-size:18px}
.title{font-size:16px;font-weight:bold;margin:8px 0}
.desc{color:#ccc;font-size:14px}
.summary{background:#2a2a00;border-radius:8px;padding:10px;margin-top:10px;font-size:14px;line-height:1.5;border:1px solid #555}
.summary b{color:#ffeb3b}
.deep{background:#0a2a4a;border-radius:8px;padding:10px;margin-top:10px;font-size:14px;line-height:1.5;border:1px solid #4da6ff}
a{color:#4da6ff;text-decoration:none;font-weight:bold;display:block;margin-top:10px}
.time{color:#888;font-size:12px}
button{background:#00c853;border:none;padding:10px 20px;border-radius:20px;font-weight:bold;font-size:16px;width:100%;margin-bottom:12px}
</style></head><body>
<h1>OTC Radar</h1>
<div class="live"><span class="dot"></span> <b id="liveText">מחובר • סורק כל הזמן</b><br><span id="lastScan">סריקה אחרונה: {{updated}}</span> • <span id="countdown">סריקה הבאה בעוד 30 שניות</span><br><span id="scanCount" style="color:#888">סריקות שבוצעו: -</span></div>
<div class="sub">10 הכי חזקות לפי ציון בלבד • לא לפי מה שהכי חדש</div>
<button onclick="location.href='/?refresh=1&t='+Date.now()">🔄 רענן עכשיו בכוח</button>
<div id="list">
{% for n in news %}
<div class="card {% if loop.index<=3 %}top{% endif %}">
<span class="score">{{n.score}}/100</span>
<div class="ticker">{{n.ticker}} • #{{loop.index}}</div>
<div class="title">{{n.title}}</div>
<div class="desc">{{n.desc}}</div>
<div class="summary"><b>למה דווקא זה?</b><br>{{n.summary}}</div>
{% if n.deep %}<div class="deep">{{n.deep}}</div>{% endif %}
<a href="{{n.link}}" target="_blank">📖 קרא את הכתבה המקורית ←</a>
<div class="time">{{n.time}} • לפני {{n.age}}</div>
</div>
{% endfor %}
</div>
<script>
let sec=30;
setInterval(()=>{
  sec--; document.getElementById('countdown').innerText='סריקה הבאה בעוד '+sec+' שניות';
  if(sec<=0){ sec=30; checkLive(); }
},1000);
async function checkLive(){
  try{
    const r=await fetch('/api/news?t='+Date.now()); const j=await r.json();
    document.getElementById('lastScan').innerText='סריקה אחרונה: '+j.last_scan;
    document.getElementById('scanCount').innerText='סריקות שבוצעו: '+j.scans;
    document.getElementById('liveText').innerText='מחובר • סורק כל הזמן • '+new Date().toLocaleTimeString('he-IL');
    const firstScore = document.querySelector('.score') ? document.querySelector('.score').innerText : '';
    if(j.news.length>0 && j.news[0].score+'/100' !== firstScore){
      location.reload();
    }
  }catch(e){ document.getElementById('liveText').innerText='מנסה להתחבר מחדש...'; }
}
setTimeout(checkLive, 2000);
</script>
</body></html>
"""

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
