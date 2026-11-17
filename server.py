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

SOURCES = []
SOURCES.append("https://news.google.com/rss/search?q=site%3Aotcmarkets.com%20stock%20news&hl=en-US&gl=US&ceid=US:en")
SOURCES.append("https://www.bing.com/news/search?q=site%3Aotcmarkets.com&format=rss")

STRONG = {}
STRONG["fda approval"] = 30
STRONG["fda"] = 20
STRONG["merger"] = 28
STRONG["acquisition"] = 28
STRONG["earnings"] = 18
STRONG["contract"] = 20
STRONG["partnership"] = 18
STRONG["uplist"] = 25
STRONG["clinical trial"] = 22
STRONG["phase 3"] = 25
STRONG["phase 2"] = 18
STRONG["breakthrough"] = 25
STRONG["patent"] = 15
STRONG["dividend"] = 15
STRONG["buyback"] = 18
STRONG["bankruptcy"] = -20
STRONG["delisting"] = -20
STRONG["reverse split"] = -15
STRONG["annual revenue"] = 30
STRONG["record annual revenue"] = 35
STRONG["revenue exceeds"] = 30
STRONG["undervalued"] = 28
STRONG["market cap"] = 12
STRONG["low market cap"] = 25
STRONG["revenue growth"] = 25
STRONG["profitable"] = 25
STRONG["net profit"] = 25
STRONG["positive cash flow"] = 28
STRONG["revenue surged"] = 28
STRONG["revenue increased"] = 22
STRONG["record revenue"] = 25
STRONG["revenue"] = 15

def get_summary_code(title, desc):
    text = (title + " " + desc).lower()
    if "revenue exceeds" in text:
        return 1
    if "annual revenue" in text:
        return 2
    if "undervalued" in text:
        return 3
    if "positive cash flow" in text:
        return 4
    if "profitable" in text:
        return 5
    if "net profit" in text:
        return 5
    if "revenue growth" in text:
        return 6
    if "fda approval" in text:
        return 7
    if "uplist" in text:
        return 8
    if "merger" in text:
        return 9
    if "acquisition" in text:
        return 9
    if "phase 3" in text:
        return 10
    if "clinical trial" in text:
        return 11
    if "record revenue" in text:
        return 12
    if "contract" in text:
        return 13
    if "partnership" in text:
        return 14
    if "dividend" in text:
        return 15
    if "bankruptcy" in text:
        return 16
    if "reverse split" in text:
        return 17
    if "delisting" in text:
        return 17
    if "breakthrough" in text:
        return 18
    if "patent" in text:
        return 19
    if "buyback" in text:
        return 20
    return 0

def get_summary_text(code):
    if code == 1:
        return "REV_EXCEEDS"
    if code == 2:
        return "ANNUAL_REV"
    if code == 3:
        return "UNDERVALUED"
    if code == 4:
        return "CASH_FLOW"
    if code == 5:
        return "PROFITABLE"
    if code == 6:
        return "REV_GROWTH"
    if code == 7:
        return "FDA_APPROVAL"
    if code == 8:
        return "UPLIST"
    if code == 9:
        return "MERGER"
    if code == 10:
        return "PHASE3"
    if code == 11:
        return "TRIAL"
    if code == 12:
        return "RECORD_REV"
    if code == 13:
        return "CONTRACT"
    if code == 14:
        return "PARTNERSHIP"
    if code == 15:
        return "DIVIDEND"
    if code == 16:
        return "BANKRUPTCY"
    if code == 17:
        return "NEGATIVE"
    if code == 18:
        return "BREAKTHROUGH"
    if code == 19:
        return "PATENT"
    if code == 20:
        return "BUYBACK"
    return "GENERAL"

def get_score(title, desc):
    text = (title + " " + desc).lower()
    score = 30
    for word in STRONG:
        pts = STRONG[word]
        if word in text:
            score = score + pts
    if "revenue" in text:
        if "market cap" in text:
            score = score + 15
        if "undervalued" in text:
            score = score + 15
    if score < 1:
        score = 1
    if score > 100:
        score = 100
    return score

def get_ticker(title, desc):
    text = title + " " + desc
    found = re.findall(r"[A-Z]{2,5}", text)
    bad = ["FDA", "CEO", "OTC", "USA", "US", "SEC", "THE", "AND", "FOR"]
    for item in found:
        if item not in bad:
            return item
    return "OTC"

def clean_text(s):
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", "", s)
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
            except Exception:
                pass
    return None

def fetch_tickwatch():
    out = []
    try:
        r = requests.get("https://tickwatch.online/", timeout=12, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            return out
        txt = r.text
        links = re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', txt, re.S)
        seen = set()
        for href, inner in links:
            title = re.sub(r"<[^>]+>", "", inner).strip()
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
            code = get_summary_code(title, title)
            summary = get_summary_text(code)
            item = {}
            item["ticker"] = ticker
            item["title"] = title
            item["desc"] = title
            item["summary"] = summary
            item["link"] = link
            item["score"] = score
            item["time"] = datetime.now().strftime("%H:%M")
            item["age"] = "TickWatch"
            out.append(item)
            if len(out) >= 10:
                break
        return out
    except Exception as e:
        print("tickwatch err")
        print(e)
        return out

def fetch_otc():
    out = []
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get("https://blog.otcmarkets.com/feed/", timeout=12, headers=headers)
        if r.status_code == 200:
            if r.content:
                root = ET.fromstring(r.content)
                items = root.findall(".//item")
                for item in items:
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
                    if pub:
                        t = pub.strftime("%H:%M")
                    else:
                        t = datetime.now().strftime("%H:%M")
                    code = get_summary_code(title, desc)
                    summary = get_summary_text(code)
                    one = {}
                    one["ticker"] = get_ticker(title, desc)
                    one["title"] = title
                    one["desc"] = desc
                    one["summary"] = summary
                    one["link"] = link
                    one["score"] = score
                    one["time"] = t
                    one["age"] = "OTC Blog"
                    out.append(one)
                    if len(out) >= 10:
                        break
    except Exception as e:
        print("otc blog err")
        print(e)
    return out

def fetch_all():
    all_news = []
    seen = set()
    now = datetime.now(timezone.utc)
    for url in SOURCES:
        try:
            r = requests.get(url, timeout=12, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code != 200:
                continue
            if not r.content:
                continue
            root = ET.fromstring(r.content)
            items = root.findall(".//item")
            if not items:
                items = []
                for e in root.iter():
                    if e.tag.endswith("entry"):
                        items.append(e)
            for item in items:
                title = item.findtext("title") or ""
                link = item.findtext("link") or "#"
                desc = item.findtext("description") or ""
                if not desc:
                    desc = item.findtext("summary") or ""
                if link == "#":
                    for child in item:
                        if child.tag.endswith("link"):
                            if child.get("href"):
                                link = child.get("href")
                                break
                if not title:
                    continue
                key = title.lower().strip()[:60]
                if key in seen:
                    continue
                seen.add(key)
                pub = parse_date(item)
                if pub:
                    age_h = (now - pub).total_seconds() / 3600
                    if age_h > 48:
                        continue
                else:
                    age_h = 999
                title = html.unescape(title.strip())
                if " - " in title:
                    title = title.rsplit(" - ", 1)[0]
                desc = clean_text(desc)
                score = get_score(title, desc)
                if pub:
                    t = pub.strftime("%H:%M")
                else:
                    t = datetime.now().strftime("%H:%M")
                if age_h < 48:
                    a = str(int(age_h)) + " hours"
                else:
                    a = "old"
                code = get_summary_code(title, desc)
                summary = get_summary_text(code)
                one = {}
                one["ticker"] = get_ticker(title, desc)
                one["title"] = title
                one["desc"] = desc
                one["summary"] = summary
                one["link"] = link
                one["score"] = score
                one["time"] = t
                one["age"] = a
                all_news.append(one)
                if len(all_news) >= 30:
                    break
        except Exception as e:
            print("err")
            print(e)
            continue
    tick = fetch_tickwatch()
    for n in tick:
        key = n["title"].lower()[:60]
        if key not in seen:
            seen.add(key)
            all_news.append(n)
    otc = fetch_otc()
    for n in otc:
        key = n["title"].lower()[:60]
        if key not in seen:
            seen.add(key)
            all_news.append(n)
    all_news = sorted(all_news, key=lambda x: x["score"], reverse=True)
    return all_news[:10]

CACHE = {}
CACHE["data"] = []
CACHE["time"] = 0
CACHE["scans"] = 0

def refresh_cache(force):
    if force:
        CACHE["data"] = []
        CACHE["time"] = 0
    need = False
    if force:
        need = True
    if time.time() - CACHE["time"] > 30:
        need = True
    if not CACHE["data"]:
        need = True
    if need:
        data = fetch_all()
        if data:
            CACHE["data"] = data
            CACHE["time"] = time.time()
            CACHE["scans"] = CACHE["scans"] + 1
        else:
            CACHE["time"] = time.time()
    return CACHE["data"]

@app.route
