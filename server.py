
import os, json, time, threading, requests, re
from flask import Flask, request, jsonify, send_from_directory
from pywebpush import webpush
import xml.etree.ElementTree as ET

app = Flask(__name__)
SUBS_FILE = "subs.json"
VAPID_PUBLIC = os.environ.get("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE = os.environ.get("VAPID_PRIVATE_KEY", "")
VAPID_CLAIMS = {"sub": "mailto:admin@example.com"}

SOURCES = [
    "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&type=8-K&count=100&output=atom",
    "https://www.otcmarkets.com/rss/news",
    "https://www.prnewswire.com/news-releases/rss/",
    "https://www.businesswire.com/portal/site/home/rss/",
    "https://www.globenewswire.com/RssFeed/subjectcode/13/feedTitle/GlobeNewswire",
    "https://www.accesswire.com/rss",
]

KEYWORDS = {
    "merger": 30, "acquisition": 30, "reverse split": 25, "uplist": 25,
    "nasdaq": 20, "fda approval": 30, "contract": 20, "patent": 15,
    "earnings": 15, "revenue": 15, "breakthrough": 20, "partnership": 18,
    "financing": 10, "offering": 5, "bankruptcy": -20,
}

latest_news = []

def load_subs():
    try:
        with open(SUBS_FILE) as f:
            return json.load(f)
    except Exception:
        return []

def save_subs(s):
    with open(SUBS_FILE, "w") as f:
        json.dump(s, f)

def score_news(title):
    t = title.lower()
    score = 40
    for k, v in KEYWORDS.items():
        if k in t:
            score += v
    if score < 0:
        score = 0
    if score > 100:
        score = 100
    return score

def fetch_rss(url):
    try:
        headers = {"User-Agent": "OTC-Radar admin@example.com", "Accept": "application/atom+xml,application/rss+xml,application/xml"}
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code != 200:
            return []
        root = ET.fromstring(r.content)
        items = []
        all_nodes = root.findall(".//item") + root.findall(".//{http://www.w3.org/2005/Atom}entry")
        for item in all_nodes:
            title_el = item.find("title")
            if title_el is None:
                title_el = item.find("{http://www.w3.org/2005/Atom}title")
            link_el = item.find("link")
            if link_el is None:
                link_el = item.find("{http://www.w3.org/2005/Atom}link")
            if title_el is None or link_el is None:
                continue
            title = title_el.text or ""
            link = link_el.text or ""
            if not link:
                link = link_el.get("href", "")
            if not title or not link:
                continue
            m = re.search(r'\((?:OTC|NASDAQ|NYSE)[: ]?([A-Z]{1,5})\)', title)
            ticker = m.group(1) if m else ""
            items.append({"title": title, "url": link, "ticker": ticker, "source": url.split("/")[2], "score": score_news(title), "time": time.strftime("%H:%M")})
        return items
    except Exception as e:
        print("RSS fail", url, e)
        return []

def send_push(title, body, url):
    subs = load_subs()
    for sub in subs:
        try:
            webpush(subscription_info=sub, data=json.dumps({"title": title, "body": body, "url": url}), vapid_private_key=VAPID_PRIVATE, vapid_claims=VAPID_CLAIMS)
        except Exception as e:
            print("push fail", e)

def scan_all():
    global latest_news
    all_items = []
    seen = set()
    for url in SOURCES:
        for n in fetch_rss(url):
            if n["url"] in seen:
                continue
            seen.add(n["url"])
            all_items.append(n)
    all_items.sort(key=lambda x: x["score"], reverse=True)
    old_urls = set()
    for x in latest_news:
        old_urls.add(x["url"])
    for n in all_items:
        if n["url"] not in old_urls and n["score"] >= 70:
            send_push("HOT " + n["ticker"] + " - " + str(n["score"]), n["title"], n["url"])
    latest_news = all_items[:50]
    print("scan done: " + str(len(latest_news)))

def loop():
    while True:
        scan_all()
        time.sleep(120)

@app.route("/")
def index():
    return send_from_directory(".", "Index.html")

@app.route("/sw.js")
def sw():
    return send_from_directory(".", "sw.js")

@app.route("/manifest.json")
def mf():
    return send_from_directory(".", "manifest.json")

@app.route("/scan-now")
def scan_now():
    return jsonify(latest_news)

@app.route("/status")
def status():
    return jsonify({"subs": len(load_subs()), "news": len(latest_news)})

@app.route("/vapid-public-key")
def vapid():
    return jsonify({"key": VAPID_PUBLIC})

@app.route("/subscribe", methods=["POST"])
def subscribe():
    subs = load_subs()
    data = request.get_json()
    if data not in subs:
        subs.append(data)
    save_subs(subs)
    return jsonify({"ok": True})

@app.route("/test-push", methods=["POST"])
def test():
    send_push("Test OTC Radar", "Notifications work", "https://otc-app1.onrender.com/")
    return jsonify({"ok": True})

threading.Thread(target=loop, daemon=True).start()
scan_all()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
