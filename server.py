import requests, re, html, time, os
from flask import Flask, render_template_string, make_response, jsonify, request
from datetime import datetime, timezone
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

app = Flask(__name__)

# === נטו 2 מקורות - RSS גיבוי של OTC ===
SOURCES = [
    "https://news.google.com/rss/search?q=site%3Aotcmarkets.com%20stock%20news&hl=en-US&gl=US&ceid=US:en",
    "https://www.bing.com/news/search?q=site%3Aotcmarkets.com&format=rss",
]

STRONG = {
    "fda approval": 30, "fda": 20, "merger": 28, "acquisition": 28,
    "acquired": 25, "earnings": 18, "contract": 20, "partnership": 18, "nasdaq uplisting": 30, "uplist": 25,
    "clinical trial": 22, "phase 3": 25, "phase 2": 18, "breakthrough": 25,
    "patent": 15, "launch": 12, "expansion": 12, "dividend": 15,
    "buyback": 18, "guidance raised": 25, "beat estimates": 20,
    "bankruptcy": -20, "delisting": -20, "reverse split": -15, "dilution": -10,
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
    if "revenue exceeds market cap" in text or "revenue exceeds" in text:
        return "💎 מחזור שנתי גבוה מהשווי - החברה מכניסה בשנה יותר ממה שהיא שווה בבורסה!"
    if "annual revenue" in text or "record annual revenue" in text:
        return "💎 מחזור שנתי חזק - תבדוק: אם המחזור השנתי קרוב לשווי השוק שלה או גדול ממנו - היא כנראה זולה מדי."
    if "undervalued" in text:
        return "💎 חברה מתומחרת בחסר - השוק נותן לה שווי נמוך ממה שהיא באמת שווה."
    if "positive cash flow" in text:
        return "💰 תזרים מזומנים חיובי - החברה באמת מכניסה כסף לחשבון."
    if "profitable" in text or "net profit" in text or "net income" in text:
        return "💰 חברה רווחית - היא לא רק מכניסה, היא גם נשארת עם רווח בסוף."
    if "revenue growth" in text or "revenue surged" in text or "revenue increased" in text:
        return "📈 צמיחה בהכנסות - החברה מכניסה כל שנה יותר."
    if "low market cap" in text:
        return "💎 שווי שוק נמוך - שווי קטן ביחס למה שהחברה עושה."
    if "fda approval" in text:
        return "🔥 אישור FDA - הטריגר הכי חזק שיש."
    if "nasdaq uplisting" in text or "uplist" in text:
        return "🔥 מעבר לנאסד״ק - עובר מ-OTC לבורסה הגדולה."
    if "merger" in text or "acquisition" in text or "acquired" in text:
        return "🔥 מיזוג / רכישה - חברה גדולה קונה אותה."
    if "phase 3" in text:
        return "💊 תוצאות שלב 3 - השלב האחרון לפני אישור FDA."
    if "clinical trial" in text or "phase 2" in text:
        return "💊 תוצאות ניסוי קליני."
    if "record revenue" in text:
        return "💰 הכנסות שיא - החברה מכניסה יותר כסף מאי פעם."
    if "guidance raised" in text or "beat estimates" in text:
        return "💰 עקפה את התחזיות והעלתה ציפיות."
    if "contract" in text:
        return "📝 חוזה חדש - כסף אמיתי שנכנס לחברה."
    if "partnership" in text:
        return "🤝 שותפות אסטרטגית."
    if "earnings" in text or "revenue" in text:
        return "📊 דוחות כספיים - תבדוק את היחס בין המחזור השנתי לשווי השוק."
    if "buyback" in text:
        return "💵 החברה קונה את המניות של עצמה."
    if "patent" in text:
        return "💡 פטנט חדש."
    if "breakthrough" in text:
        return "🚀 פריצת דרך."
    if "dividend" in
