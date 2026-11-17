
import requests
import re
import html
import time
import os
from flask import Flask, render_template_string, make_response, jsonify, request
from datetime import datetime, timezone
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

app = Flask(__name__)
CACHE_DATA = []
CACHE_TIME = 0

def get_score(title):
    t = title.lower()
    s = 30
    if "fda approval" in t:
        s = s + 30
    if "merger" in t:
        s = s + 28
    if "annual revenue" in t:
        s = s + 30
    if "undervalued" in t:
        s = s + 28
    if "contract" in t:
        s = s + 20
    if "bankruptcy" in t:
        s = s - 20
    if s > 100:
        s = 100
    if s < 1:
        s = 1
    return s

def get_ticker(title):
    m = re.findall(r"[A-Z]{2,5}", title)
    for x in m:
        if x not in ["FDA", "CEO", "OTC", "USA", "US", "SEC", "THE", "AND", "FOR"]:
            return x
    return "OTC"

def clean(s):
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    return s[:200]

def fetch_all():
    out = []
    seen = set()
    urls = []
    urls.append("https://news.google.com/rss/search?q=otcmarkets+stock&hl=en-US&gl=US&ceid=US:en")
    urls.append("https://blog.otcmarkets.com/feed/")
    for url in urls:
        try:
            r = requests.get(url, timeout=12, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code != 200:
                continue
            root = ET.fromstring(r.content)
            items = root.findall(".//item")
            for item in items:
                title = item.findtext("title") or ""
                link = item.findtext("link") or "#"
                desc = item.findtext("description") or ""
                if not title:
                    continue
                k = title.lower()[:60]
                if k in seen:
                    continue
                seen.add(k)
                title2 = html.unescape(title.strip())
                if " - " in title2:
                    title2 = title2.rsplit(" - ", 1)[0]
                d = {}
                d["ticker"] = get_ticker(title2)
                d["title"] = title2
                d["desc"] = clean(desc)
                d["summary"] = "GENERAL"
                d["link"] = link
                d["score"] = get_score(title2)
                d["time"] = datetime.now().strftime("%H:%M")
                d["age"] = "RSS"
                out.append(d)
        except Exception as e:
            print(e)
            continue
    out = sorted(out, key=lambda x: x["score"], reverse=True)
    return out[:10]

def get_data(force):
    global CACHE_DATA, CACHE_TIME
    if force:
        CACHE_DATA = []
        CACHE_TIME = 0
    if force or not CACHE_DATA or time.time() - CACHE_TIME > 30:
        d = fetch_all()
        if d:
            CACHE_DATA = d
            CACHE_TIME = time.time()
    return CACHE_DATA

@app.route("/api/news")
def api_news():
    d = get_data(False)
    return jsonify({"news": d})

@app.route("/")
def home():
    force = False
    if request.args.get("refresh") == "1":
        force = True
    news = get_data(force)
    h = render_template_string(PAGE, news=news, updated=datetime.now().strftime("%H:%M:%S"))
    resp = make_response(h)
    resp.headers["Cache-Control"] = "no-cache"
    return resp

PAGE = "<html dir='rtl'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>OTC Radar</title><style>body{background:#0a0a0a;color:#fff;font-family:Arial;padding:15px}.card{background:#1a1a1a;border-radius:12px;padding:14px;margin-bottom:12px;border-right:5px solid #00c853}button{background:#00c853;border:none;padding:10px;border-radius:20px;font-weight:bold;width:100%}</style></head><body><h1>OTC Radar</h1><div>סריקה: {{updated}}</div><a href='/?refresh=1'><button>רענן עכשיו בכוח</button></a>{% for n in news %}<div class='card'><b>{{n.ticker}} - {{n.score}}/100</b><div>{{n.title}}</div><div>{{n.desc}}</div><a href='{{n.link}}' target='_blank'>קרא כתבה</a><div>{{n.time}}</div></div>{% endfor %}{% if not news %}<p>סורק... לחץ רענן</p>{% endif %}</body></html>"

if __name__ == "__main__":
    p = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=p)
