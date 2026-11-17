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
        return "מחזור גבוה מהשווי - החברה מכניסה יותר ממה שהיא שווה"
    if "annual revenue" in text:
        return "מחזור שנתי חזק - תבדוק אם המחזור קרוב לשווי השוק"
    if "undervalued" in text:
        return "חברה מתומחרת בחסר - שווי נמוך ממה שהיא שווה"
    if "positive cash flow" in text:
        return "תזרים מזומנים חיובי - החברה באמת מכניסה כסף"
    if "profitable" in text:
        return "חברה רווחית - נשארת עם רווח בסוף"
    if "net profit" in text:
        return "חברה רווחית - נשארת עם רווח בסוף"
    if "revenue growth" in text:
        return "צמיחה בהכנסות"
    if "revenue surged" in text:
        return "צמיחה בהכנסות"
    if "fda approval" in text:
        return "אישור FDA - הטריגר הכי
