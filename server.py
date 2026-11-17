import requests, re, html, time, os
from flask import Flask, render_template_string, make_response, jsonify, request
from datetime import datetime, timezone
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

app = Flask(__name__)

SOURCES = [
    # === TickWatch - המקסימום החינמי ===
    "https://news.google.com/rss/search?q=site%3Atickwatch.online&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=site%3Atickwatch.online%20revenue%20OR%20undervalued%20OR%20earnings&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=site%3Atickwatch.online%20FDA%20OR%20merger%20OR%20uplisting&hl=en-US&gl=US&ceid=US:en",
    "https://www.bing.com/news/search?q=site%3Atickwatch.online&format=rss",
    # === OTC Markets - האתר הרשמי ===
    "https://news.google.com/rss/search?q=site%3Aotcmarkets.com%20stock%20news&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=site%3Aotcmarkets.com%20revenue%20OR%20earnings%20OR%20OTCQX&hl=en-US&gl=US&ceid=US:en",
    "https://www.bing.com/news/search?q=site%3Aotcmarkets.com&format=rss",
    # === מחזור שנתי חיובי ביחס לשווי - החדש שלך ===
    "https://news.google.com/rss/search?q=OTC%20%22annual%20revenue%22%20%22market%20cap%22%20stock&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=penny%20stock%20%22revenue%20exceeds%22%20OR%20%22undervalued%22%20OR%20%22profitable%22&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=OTC%20stock%20%22positive%20cash%20flow%22%20OR%20%22record%20annual%20revenue%22&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=OTC%20%22revenue%20growth%22%20%22market%20capitalization%22&hl=en-US&gl=US&ceid=US:en",
    # === כללי - חזק ===
    "https://news.google.com/rss/search?q=%22FDA%20approval%22%20stock&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=OTC%20merger%20OR%20acquisition%20stock&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=nasdaq%20uplisting%20OTC&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=OTC%20stocks%20earnings%20OR%20contract%20OR%20partnership&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=penny%20stocks%20breakthrough%20OR%20clinical%20trial&hl=en-US&gl=US&ceid=US:en",
    "https://www.globenewswire.com/RssFeed/subjectcode/13/OTC%20Markets/feed.xml",
    "https://www.accesswire.com/rss",
]

STRONG = {
    # FDA / מיזוג
    "fda approval": 30, "fda": 20, "merger": 28, "acquisition": 28,
    "acquired": 25, "earnings": 18, "contract": 20, "partnership": 18, "nasdaq uplisting": 30, "uplist": 25,
    "clinical trial": 22, "phase 3": 25, "phase 2": 18, "breakthrough": 25,
    "patent": 15, "launch": 12, "expansion": 12, "dividend": 15,
    "buyback": 18, "guidance raised": 25, "beat estimates": 20,
    "bankruptcy": -20, "delisting": -20, "reverse split": -15, "dilution": -10,
    # === מחזור שנתי חיובי ביחס לשווי - החדש ===
    "annual revenue": 30, "record annual revenue": 35, "annual revenue growth": 30,
    "revenue exceeds": 30, "revenue exceeds market cap": 35,
    "undervalued": 28, "undervalued stock": 30, "significantly undervalued": 32,
    "market cap": 12, "market capitalization": 12, "low market cap": 25,
    "revenue growth": 25, "strong revenue growth": 28,
    "profitable": 25, "profitability": 25, "net profit": 25, "net income": 22,
    "positive cash flow": 28, "positive operating cash flow": 30,
    "revenue of $": 20, "revenue increased": 22, "revenue surged": 28,
    "revenue up": 20, "sales growth": 22, "record sales": 25,
    "otcqx": 12, "otcqb": 10, "uplisted to otcqx": 20,
    "revenue": 15, "record revenue": 25,
}

def hebrew_summary(title, desc):
    text = (title + " " + desc).lower()
    # מחזור שנתי ביחס לשווי - קודם כל, כי זה מה שביקשת
    if "revenue exceeds market cap" in text or "revenue exceeds" in text:
        return "💎 מחזור שנתי גבוה מהשווי - החברה מכניסה בשנה יותר ממה שהיא שווה בבורסה! זה אומר שהיא זולה בטירוף ביחס לכמה כסף היא באמת עושה."
    if "annual revenue" in text or "record annual revenue" in text:
        return "💎 מחזור שנתי חזק - ההכנסה השנתית של החברה גבוהה. תבדוק: אם המחזור השנתי קרוב לשווי השוק שלה או גדול ממנו - היא כנראה זולה מדי והשוק עוד לא תמחר אותה נכון."
    if "undervalued" in text:
        return "💎 חברה מתומחרת בחסר - השוק נותן לה שווי נמוך ממה שהיא באמת שווה לפי ההכנסות והרווחים שלה. זה בדיוק המקום שבו מוצאים מציאות."
    if "positive cash flow" in text:
        return "💰 תזרים מזומנים חיובי - החברה באמת מכניסה כסף לחשבון, לא רק על הנייר. זה מה שמבדיל חברה אמיתית מחברת חלום."
    if "profitable" in text or "net profit" in text or "net income" in text:
        return "💰 חברה רווחית - היא לא רק מכניסה, היא גם נשארת עם רווח בסוף. ב-OTC זה נדיר וזה מה שמקפיץ מניות."
    if "revenue growth" in text or "revenue surged" in text or "revenue increased" in text:
        return "📈 צמיחה בהכנסות - החברה מכניסה כל שנה יותר מהשנה הקודמת. אם השווי שלה לא עלה באותו קצב - היא נהייתה זולה יותר."
    if "low market cap" in text:
        return "💎 שווי שוק נמוך - שווי קטן ביחס למה שהחברה עושה. שילוב של שווי נמוך + הכנסות גבוהות = פוטנציאל גדול."
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
        return "📊 דוחות כספיים - זה הרגע שבו רואים אם החברה באמת מרוויחה. תבדוק את היחס בין המחזור השנתי לשווי השוק."
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
    # בונוס מיוחד - אם יש גם הכנסה וגם שווי נמוך באותה חדשה, זה בדיוק מה שאתה מחפש
    if ("revenue" in text or "annual revenue" in text) and ("market cap" in text or "undervalued" in text or "low market" in text):
        score += 15
    if "tickwatch" in text or "otcmarkets" in text:
        score += 5
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
    s = html.unescape(s)
    s = re.sub(r'\s*-\s*[A-Za-z ]+$', '', s)
    return s[:200]

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
                dt = parsedate_to_datetime(child.text)
                if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except: pass
    return None

def fetch_tickwatch_sitemap_best():
    out = []
    urls_to_try = [
        "https://tickwatch.online/sitemap.xml",
        "https://tickwatch.online/sitemap_index.xml",
        "https://tickwatch.online/wp-sitemap.xml",
        "https://tickwatch.online/rss.xml",
        "https://tickwatch.online/feed",
        "https://tickwatch.online/",
    ]
    headers = {"User-Agent": "Mozilla/5.0"}
    for u in urls_to_try:
        try:
            r = requests.get(u, timeout=10, headers=headers)
            if r.status_code != 200 or not r.text: continue
            txt = r.text
            if "<url" in txt or "<loc>" in txt:
                locs = re.findall(r'<loc>(.*?)</loc>', txt)
                for loc in locs[-10:]:
                    m = re.search(r'/([A-Z]{2,5})', loc)
                    ticker = m.group(1) if m else get_ticker(loc, "")
                    title = loc.split("/")[-1].replace("-", " ").replace(".html","").title()
                    if len(title) < 5: title = f"TickWatch - {ticker}"
                    out.append({
                        "ticker": ticker, "title": title[:120],
                        "desc": "חדש ב-TickWatch - נמצא במפת האתר",
                        "summary": "👀 חדש ב-TickWatch - נמצא ישירות במפת האתר, בלי לחכות לגוגל.",
                        "link": loc, "score": 50,
                        "time": datetime.now().strftime("%H:%M"), "age": "עכשיו"
                    })
                if out: break
            elif "tickwatch" in u and u.endswith("/"):
                tickers = re.findall(r'\b([A-Z]{2,5})\b', txt)
                seen = set()
                for tk in tickers:
                    if tk in ["FDA","CEO","OTC","USA","SEC","THE","AND","FOR","SOS","API","NEWS","HOME"] or tk in seen: continue
                    seen.add(tk)
                    out.append({
                        "ticker": tk, "title": f"TickWatch - {tk} on watchlist",
                        "desc": "מופיע ברשימת המעקב של TickWatch",
                        "summary": "👀 מופיע ב-TickWatch ברשימת המעקב החמה.",
                        "link": "https://tickwatch.online/", "score": 45,
                        "time": datetime.now().strftime("%H:%M"), "age": "עכשיו"
                    })
                    if len(out) >= 5: break
        except: continue
        if out: break
    return out[:5]

def fetch_all():
    all_news = []
    seen_titles = set()
    now = datetime.now(timezone.utc)
    for url in SOURCES:
        try:
            r = requests.get(url, timeout=12, headers={"User-Agent": "Mozilla/5.0", "Cache-Control": "no-cache"})
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
                key = title.lower().strip()[:60]
                if key in seen_titles: continue
                seen_titles.add(key)
                pub = parse_date(item)
                if pub:
                    age_hours = (now - pub).total_seconds() / 3600
                    if age_hours > 48: continue
                else:
                    age_hours = 999
                title = html.unescape(title.strip())
                if " - " in title:
                    title = title.rsplit(" - ", 1)[0]
                desc = clean_text(desc)
                score = get_score(title, desc)
                if score < 35: continue
                all_news.append({
                    "ticker": get_ticker(title, desc),
                    "title": title, "desc": desc,
                    "summary": hebrew_summary(title, desc),
                    "link": link if link else "#",
                    "score": score,
                    "time": pub.strftime("%H:%M") if pub else datetime.now().strftime("%H:%M"),
                    "age": f"{int(age_hours)} שעות" if age_hours < 48 else "ישן"
                })
        except Exception as e:
            print("err", url, e); continue
    tw = fetch_tickwatch_sitemap_best()
    for t in tw:
        if t["ticker"] not in [n["ticker"] for n in all_news]:
            all_news.append(t)
    all_news = sorted(all_news, key=lambda x: x["score"], reverse=True)
    return all_news[:10]

CACHE = {"data": [], "time": 0, "scans": 0}

def refresh_cache(force=False):
    if force or time.time() - CACHE["time"] > 120 or not CACHE["data"]:
        data = fetch_all()
        if data:
            CACHE["data"] = data
            CACHE["time"] = time.time()
            CACHE["scans"] += 1
    return CACHE["data"]

@app.route("/api/news")
def api_news():
    data = refresh_cache()
    return jsonify({"news": data, "last_scan": datetime.now().strftime("%H:%M:%S"), "scans": CACHE["scans"], "server_time": time.time()})

@app.route("/")
def home():
    force = request.args.get("refresh") == "1"
    news = refresh_cache(force=force)
    html_out = render_template_string(HTML, news=news, updated=datetime.now().strftime("%H:%M:%S"))
    resp = make_response(html_out)
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
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
a{color:#4da6ff;text-decoration:none;font-weight:bold;display:block;margin-top:10px}
.time{color:#888;font-size:12px}
button{background:#00c853;border:none;padding:10px 20px;border-radius:20px;font-weight:bold;font-size:16px;width:100%;margin-bottom:12px}
</style></head><body>
<h1>OTC Radar</h1>
<div class="live"><span class="dot"></span> <b id="liveText">מחובר • סורק כל הזמן</b><br><span id="lastScan">סריקה אחרונה: {{updated}}</span> • <span id="countdown">סריקה הבאה בעוד 30 שניות</span><br><span id="scanCount" style="color:#888">סריקות שבוצעו: -</span></div>
<div class="sub">10 הכי חזקות • כולל TickWatch + OTC Markets • מחזור שנתי vs שווי שוק • חינמי</div>
<a href="/?refresh=1"><button>🔄 רענן עכשיו בכוח</button></a>
<div id="list">
{% for n in news %}
<div class="card {% if loop.index<=3 %}top{% endif %}">
<span class="score">{{n.score}}/100</span>
<div class="ticker">{{n.ticker}} • #{{loop.index}}</div>
<div class="title">{{n.title}}</div>
<div class="desc">{{n.desc}}</div>
<div class="summary"><b>למה דווקא זה?</b><br>{{n.summary}}</div>
<a href="{{n.link}}" target="_blank">📖 קרא את הכתבה המקורית ←</a>
<div class="time">{{n.time}} • לפני {{n.age}}</div>
</div>
{% endfor %}
</div>
{% if not news %}<p style="text-align:center">סורק מקורות... לחץ רענן בעוד דקה.</p>{% endif %}
<script>
let sec=30;
setInterval(()=>{
  sec--; document.getElementById('countdown').innerText='סריקה הבאה בעוד '+sec+' שניות';
  if(sec<=0){ sec=30; checkLive(); }
},1000);
async function checkLive(){
  try{
    const r=await fetch('/api/news'); const j=await r.json();
    document.getElementById('lastScan').innerText='סריקה אחרונה: '+j.last_scan;
    document.getElementById('scanCount').innerText='סריקות שבוצעו: '+j.scans;
    document.getElementById('liveText').innerText='מחובר • סורק כל הזמן • '+new Date().toLocaleTimeString('he-IL');
    const firstScore = document.querySelector('.score') ? document.querySelector('.score').innerText : '';
    if(j.news.length>0 && j.news[0].score+'/100' !== firstScore){ location.reload(); }
    if(j.news.length>0 && !document.querySelector('.score')){ location.reload(); }
  }catch(e){ document.getElementById('liveText').innerText='מנסה להתחבר מחדש...'; }
}
setTimeout(checkLive, 2000);
</script>
</body></html>
"""

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
