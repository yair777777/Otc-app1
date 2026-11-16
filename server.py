import os, json, time, threading, requests, re
from flask import Flask, request, jsonify, send_from_directory
from pywebpush import webpush, WebPushException
import xml.etree.ElementTree as ET

app = Flask(__name__)
SUBS_FILE = "subs.json"
VAPID_PUBLIC = os.environ.get("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE = os.environ.get("VAPID_PRIVATE_KEY", "")
VAPID_CLAIMS = {"sub": "mailto:admin@example.com"}

# 6 מקורות אמינים בלבד - מהחברה עצמה
SOURCES = [
    # 1. SEC EDGAR - דיווחים רשמיים 8-K
    "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&type=8-K&count=100&output=atom",
    # 2. OTC Markets Disclosure
    "https://www.otcmarkets.com/rss/news",
    # 3. PR Newswire
    "https://www.prnewswire.com/news-releases/rss/",
    # 4. BusinessWire
    "https://www.businesswire.com/portal/site/home/rss/",
    # 5. GlobeNewswire
    "https://www.globenewswire.com/RssFeed/subjectcode/13/feedTitle/GlobeNewswire",
    # 6. AccessWire
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
        with open(SUBS_FILE) as f: return json.load(f)
    except: return []

def save_subs(s):
    with open(SUBS_FILE, "w") as f: json.dump(s, f)

def score_news(title):
    t = title.lower()
    score = 40
    for k, v in KEYWORDS.items():
        if k in t: score += v
    return max(0, min(100, score))

def fetch_rss(url):
    try:
        headers = {"User-Agent": "OTC-Radar admin@example.com", "Accept": "application/atom+xml,application/rss+xml,application/xml"}
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code != 200: return []
        root = ET.fromstring(r.content)
        items = []
        # RSS + Atom
        for item in root.findall(".//item") + root.findall(".//{http://www.w3.org/2005/Atom}entry"):
            title_el = item.find("title") if item.find("title") is not None else item.find("{http://www.w3.org/2005/Atom}title")
            link_el = item.find("link") if item.find("link") is not None else item.find("{http://www.w3.org/2005/Atom}link")
            title = title_el.text if title_el is not None else ""
            link = ""
            if link_el is not None:
                link = link_el.text or link_el.get("href", "")
            if not title or not link: continue
            # ח
