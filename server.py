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
    return "👀 חדשה עם עניין בשוק."

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

def fetch_all():
    all_news = []
    now = datetime.now(timezone.utc)
    DEBUG_LOG["sources"] = []
    start = time.time()
    for url in SOURCES:
        # תיקון הבאג: אם עברו 20 שניות בסך הכל - עוצרים, לא מחכים למקור איטי
        if time.time() - start > 20:
            break
        src_info = {"url": url, "status": 0, "found": 0, "kept": 0, "error": ""}
        try:
            headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/rss+xml, application/xml, application/atom+xml, text/xml, */*", "Cache-Control": "no-cache"}
            if "sec.gov" in url:
                headers["User-Agent"] = "OTC-Radar contact@example.com"
            # תיקון הבאג: 6 שניות ולא 15 - מקור איטי לא הורג את האתר
            r = requests.get(url, timeout=6, headers=headers)
            src_info["status"] = r.status_code
            if r.status_code != 200 or not r.content:
                src_info["error"] = f"status {r.status_code}"
                DEBUG_LOG["sources"].append(src_info)
                continue
            try:
                root = ET.fromstring(r.content)
            except Exception as e:
                src_info["error"] = f"XML fail: {str(e)[:80]}"
                DEBUG_LOG["sources"].append(src_info)
                continue
            items = []
            for e in root.iter():
                tn = e.tag.split('}')[-1].lower()
                if tn in ("item", "entry"):
                    items.append(e)
            src_info["found"] = len(items)
            for item in items[:30]:
                title = _get_child_text(item, ["title"])
                link = _get_child_text(item, ["link"])
                desc = _get_child_text(item, ["description", "summary", "content"])
                if not title:
                    continue
                pub = parse_date(item)
                if pub:
                    age_hours = (now - pub).total_seconds() / 3600
                    if age_hours > 168:
                        continue
                else:
                    age_hours = 999
                title = html.unescape(title.strip())
                desc = clean_text(desc)
                all_news.append({
                    "ticker": get_ticker(title, desc), "title": title, "desc": desc,
                    "summary": hebrew_summary(title, desc),
                    "link": link if link else "#", "score": get_score(title, desc),
                    "time": pub.strftime("%H:%M") if pub else datetime.now().strftime("%H:%M"),
                    "age": f"{int(age_hours)} שעות" if age_hours < 168 else "ישן",
                    "deep": ""
                })
                src_info["kept"] += 1
        except Exception as e:
            src_info["error"] = str(e)[:150]
        DEBUG_LOG["sources"].append(src_info)
    DEBUG_LOG["last_fetch"] = datetime.now().strftime("%H:%M:%S")
    DEBUG_LOG["total"] = len(all_news)
    all_news = sorted(all_news, key=lambda x: x["score"], reverse=True)
    # בדיקה עמוקה - רק 3, עם timeout קצר, שלא תתקע את הסריקה
    deep_count = 0
    for n in all_news[:10]:
        if deep_count >= 3:
            break
        if time.time() - start > 25:
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
    all_news = sorted(all_news, key=lambda x: x["score"], reverse=True)
    return all_news[:10]

CACHE = {"data": [], "time": 0, "scans": 0}

def refresh_cache(force=False):
    if force:
        CACHE["time"] = 0
    if force or time.time() - CACHE["time"] > 120 or not CACHE["data"]:
        try:
            data = fetch_all()
        except Exception as e:
            print("fetch_all crash", e)
            data = []
        CACHE["time"] = time.time()
        CACHE["scans"] += 1
        if data:
            CACHE["data"] = data
    return CACHE["data"]

@app.route("/health")
def health():
    return "OK", 200

@app.route("/api/debug")
def api_debug():
    return jsonify(DEBUG_LOG)

@app.route("/api/news")
def api_news():
    try:
        force = request.args.get("force") == "1"
        data = refresh_cache(force=force)
        return jsonify({"news": data, "last_scan": datetime.now().strftime("%H:%M:%S"), "scans": CACHE["scans"]})
    except Exception as e:
        return jsonify({"news": [], "error": str(e)}), 200

@app.route("/")
def home():
    # תיקון הבאג הכי חשוב: דף הבית לא מחכה לסריקה בכלל - נטען מיד
    # החדשות נטענות אחר כך דרך JS מ-/api/news
    # ככה האתר אף פעם לא נתקע על מקור איטי
    html_out = render_template_string(HTML, news=[], updated=datetime.now().strftime("%H:%M:%S"))
    resp = make_response(html_out)
    resp.headers["Cache-Control"] = "no-cache"
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
.empty{background:#2a1a1a;border:1px solid #ff5252;border-radius:12px;padding:20px;text-align:center;margin-top:20px}
a{color:#4da6ff;text-decoration:none;font-weight:bold;display:block;margin-top:10px}
.time{color:#888;font-size:12px}
button{background:#00c853;border:none;padding:10px 20px;border-radius:20px;font-weight:bold;font-size:16px;width:100%;margin-bottom:12px}
</style></head><body>
<h1>OTC Radar</h1>
<div class="live"><span class="dot"></span> <b id="liveText">מחובר • סורק כל הזמן</b><br><span id="lastScan">טוען...</span> • <span id="countdown">סריקה הבאה בעוד 30 שניות</span><br><span id="scanCount">סריקות שבוצעו: -</span></div>
<div class="sub">10 הכי חזקות לפי ציון בלבד • רק הודעות רשמיות של החברות</div>
<button onclick="loadNews(true)">🔄 רענן עכשיו בכוח</button>
<div id="list"><div class="empty">⏳ טוען חדשות... אם זה לא נטען תוך 10 שניות, רענן את הדף</div></div>
<script>
let sec=30;
function renderNews(news){
  const el=document.getElementById('list');
  if(!news || news.length===0){ el.innerHTML='<div class="empty">⚠️ הסורק לא מצא חדשות בסריקה האחרונה<br><a href="/api/debug" target="_blank">פתח דף בדיקה</a></div>'; return; }
  el.innerHTML = news.map((n,i)=>{
    return '<div class="card '+(i<3?'top':'')+'"><span class="score">'+n.score+'/100</span><div class="ticker">'+n.ticker+' • #'+(i+1)+'</div><div class="title">'+n.title+'</div><div class="desc">'+(n.desc||'')+'</div><div class="summary"><b>למה דווקא זה?</b><br>'+n.summary+'</div>'+(n.deep?'<div class="deep">'+n.deep+'</div>':'')+'<a href="'+n.link+'" target="_blank">📖 קרא את הכתבה המקורית ←</a><div class="time">'+n.time+' • לפני '+n.age+'</div></div>';
  }).join('');
}
async function loadNews(force){
  try{
    const r=await fetch('/api/news?force='+(force?'1':'0')+'&t='+Date.now()); const j=await r.json();
    document.getElementById('lastScan').innerText='סריקה אחרונה: '+j.last_scan;
    document.getElementById('scanCount').innerText='סריקות שבוצעו: '+j.scans;
    document.getElementById('liveText').innerText='מחובר • סורק כל הזמן • '+new Date().toLocaleTimeString('he-IL');
    renderNews(j.news);
  }catch(e){ document.getElementById('liveText').innerText='מנסה להתחבר מחדש...'; }
}
setInterval(()=>{ sec--; document.getElementById('countdown').innerText='סריקה הבאה בעוד '+sec+' שניות'; if(sec<=0){ sec=30; loadNews(false); } },1000);
loadNews(false);
</script>
</body></html>
"""

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
