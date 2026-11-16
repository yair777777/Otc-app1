import requests, re, html, time, os
from flask import Flask, render_template_string
from datetime import datetime
import xml.etree.ElementTree as ET

app = Flask(__name__)

SOURCES = [
    "https://www.otcmarkets.com/news/rss",
    "https://finance.yahoo.com/rss/topstories",
    "https://www.globenewswire.com/RssFeed/subjectcode/13/OTC%20Markets/feed.xml",
    "https://www.accesswire.com/rss",
    "https://www.stocktitan.net/rss/",
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s=OTC&region=US&lang=en-US",
]

STRONG = {
    "fda approval": 30, "fda": 20, "merger": 28, "acquisition": 28,
    "acquired": 25, "earnings": 18, "revenue": 15, "record revenue": 25,
    "contract": 20, "partnership": 18, "nasdaq uplisting": 30, "uplist": 25,
    "clinical trial": 22, "phase 3": 25, "phase 2": 18, "breakthrough": 25,
    "patent": 15, "launch": 12, "expansion": 12, "dividend": 15,
    "buyback": 18, "guidance raised": 25, "beat estimates": 20,
    "bankruptcy": -20, "delisting": -20, "reverse split": -15, "dilution": -10
}

def get_score(title, desc):
    text = (title + " " + desc).lower()
    score = 30
    for word, pts in STRONG.items():
        if word in text:
            score += pts
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

def fetch_all():
    all_news = []
    for url in SOURCES:
        try:
            r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code != 200 or not r.content:
                continue
            root = ET.fromstring(r.content)
            # תומך גם ב-RSS (item) וגם ב-Atom (entry)
            items = root.findall(".//item")
            if not items:
                # Atom עם namespace
                items = [e for e in root.iter() if e.tag.endswith('entry')]
            for item in items[:20]:
                # RSS
                title = item.findtext("title") or ""
                link = item.findtext("link") or "#"
                desc = item.findtext("description") or item.findtext("summary") or ""
                # Atom - link הוא attribute
                if link == "#" or not link:
                    for child in item:
                        if child.tag.endswith('link') and child.get('href'):
                            link = child.get('href')
                            break
                if not title:
                    continue
                title = html.unescape(title.strip())
                desc = clean_text(desc)
                score = get_score(title, desc)
                all_news.append({
                    "ticker": get_ticker(title, desc),
                    "title": title,
                    "desc": desc,
                    "link": link if link else "#",
                    "score": score,
                    "time": datetime.now().strftime("%H:%M")
                })
        except Exception as e:
            print("err", url, e)
            continue
    all_news = sorted(all_news, key=lambda x: x["score"], reverse=True)
    return all_news[:10]

CACHE = {"data": [], "time": 0}

@app.route("/")
def home():
    if time.time() - CACHE["time"] > 120 or not CACHE["data"]:
        data = fetch_all()
        if data:  # שומר רק אם יש נתונים, לא דורס עם ריק
            CACHE["data"] = data
            CACHE["time"] = time.time()
    news = CACHE["data"]
    return render_template_string(HTML, news=news, updated=datetime.now().strftime("%H:%M:%S"))

HTML = """
<!DOCTYPE html><html dir="rtl" lang="he"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>OTC Radar</title>
<style>
body{background:#0a0a0a;color:#fff;font-family:Arial;padding:15px}
h1{text-align:center;margin:5px} .sub{text-align:center;color:#aaa;margin-bottom:15px}
.card{background:#1a1a1a;border-radius:12px;padding:14px;margin-bottom:12px;border-right:5px solid #00c853}
.card.top{border-right-color:#ff9800}
.score{float:left;background:#00c853;color:#000;font-weight:bold;padding:5px 10px;border-radius:20px;font-size:18px}
.ticker{color:#00e676;font-weight:bold;font-size:18px}
.title{font-size:16px;font-weight:bold;margin:8px 0}
.desc{color:#ccc;font-size:14px}
a{color:#4da6ff;text-decoration:none;font-weight:bold;display:block;margin-top:10px}
.time{color:#888;font-size:12px}
</style></head><body>
<h1>OTC Radar</h1><div class="sub">10 הכי חזקות עכשיו בשוק | עודכן: {{updated}}</div>
{% for n in news %}
<div class="card {% if loop.index<=3 %}top{% endif %}">
<span class="score">{{n.score}}/100</span>
<div class="ticker">{{n.ticker}} • #{{loop.index}}</div>
<div class="title">{{n.title}}</div>
<div class="desc">{{n.desc}}</div>
<a href="{{n.link}}" target="_blank">📖 קרא את הכתבה המקורית ←</a>
<div class="time">{{n.time}}</div>
</div>
{% endfor %}
{% if not news %}<p style="text-align:center">בודק מקורות... רענן בעוד דקה. אם זה ממשיך, אחד המקורות חסום כרגע.</p>{% endif %}
<script>setTimeout(()=>location.reload(),120000)</script>
</body></html>
"""

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
