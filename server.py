import json
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pywebpush import webpush

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

VAPID_PRIVATE_KEY = "0mItWJfrpdBnghUtlFQ8nCJd1Ip5hMjqEWVdEH1h4_w"
VAPID_CLAIMS = {"sub": "mailto:you@otcradar.com"}
subscribers = []

class Subscription(BaseModel):
    subscription: dict

@app.get("/")
def home():
    return {"status": "OTC Radar LIVE", "subscribers": len(subscribers)}

@app.post("/subscribe")
def subscribe(sub: Subscription):
    if sub.subscription not in subscribers:
        subscribers.append(sub.subscription)
    return {"ok": True}

@app.get("/alerts")
def get_alerts():
    return []
