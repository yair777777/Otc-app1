import os, json, time, threading, re, requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from pywebpush import webpush, WebPushException

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

VAPID_PUBLIC = os.environ.get('VAPID_PUBLIC_KEY', '')
VAPID_PRIVATE = os.environ.get('VAPID_PRIVATE_KEY', '')
VAPID_SUBJECT = os.environ.get('VAPID_SUBJECT', 'mailto:you@gmail.com')

SUBS_FILE = 'subs.json'

def load_subs():
    try:
        with open(SUBS_FILE) as f:
            return json.load(f)
    except:
        return []

def save_subs(s):
    with open(SUBS_FILE, 'w') as f:
        json.dump(s, f)

sent_ids = set()

KEYWORDS = {
    'fda approval': 95, 'fda approved': 95, 'uplist': 90, 'nasdaq': 90, 'nyse': 90,
    'merger': 85, 'acquisition': 85, 'acquired': 85, 'contract': 80, 'awarded': 80,
    'revenue': 75, 'record revenue': 88, 'earnings': 70, 'patent': 75, 'partnership': 78,
    'agreement': 72, 'clinical trial': 82, 'phase 3': 82, 'breakthrough': 88,
    'buyback': 80, 'dividend': 70, 'financing': 55, 'offering': 45, 'dilution': 30
}

def score(title):
    t = title.lower()
    s = 40
    for k, v in KEYWORDS.items():
        if k in t:
            s = max(s, v)
    if 'otc' in t:
        s += 5
    return min(s, 99)

def send_push(sub, title, body, url):
    try:
        webpush(subscription_info=sub, data=json.dumps({'title': title, 'body': body, 'url': url}),
                vapid_private_key=VAPID_PRIVATE, vapid_claims={'sub': VAPID_SUBJECT})
        return True
    except Exception as e:
        print('push fail', e)
        return False

def fetch_sec():
    out = []
    try:
        r = requests.get('https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=8-K&count=40&output=atom', headers={'User-Agent': 'OtcScanner you@gmail.com'}, timeout=15)
        for m in re.findall(r'<title>(.*?)</title>.*?<link.*?href="(.*?)"', r.text, re.S):
            out.append((m[0].strip(), m[1]))
    except Exception as e:
        print(e)
    return out

def fetch_globe():
    out = []
    try:
        r = requests.get('https://www.globenewswire.com/RssFeed/subjectcode/1-OTC%20Markets', timeout=15)
        for m in re.findall(r'<title>(.*?)</title>.*?<link>(.*?)</link>', r.text, re.S):
            out.append((m[0].strip(), m[1].strip()))
    except Exception as e:
        print(e)
    return out

def scanner_loop():
    while True:
        try:
            items = fetch_sec() + fetch_globe()
            subs = load_subs()
            for title, url in items:
                if url in sent_ids:
                    continue
                sc = score(title)
                if sc >= 75 and subs:
                    sent_ids.add(url)
                    for sub in subs:
                        send_push(sub, 'OTC ALERT ' + str(sc) + '% - ' + title[:80], 'Score: ' + str(sc) + '% | ' + title, url)
                    print('SENT', sc, title)
                elif sc >= 75:
                    sent_ids.add(url)
                    print('WOULD SEND no subs', sc, title)
        except Exception as e:
            print('loop err', e)
        time.sleep(120)

@app.route('/')
def home():
    try:
        with open('Index.html', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return 'ERROR: ' + str(e) + ' | FILES: ' + str(os.listdir('.'))

@app.route('/status')
def status():
    return jsonify({'status': 'live', 'subs': len(load_subs()), 'vapid_public': VAPID_PUBLIC[:10] + '...'})

@app.route('/vapid-public-key')
def vapid():
    return jsonify({'key': VAPID_PUBLIC})

@app.route('/subscribe', methods=['POST'])
def sub():
    data = request.json
    subs = load_subs()
    if data not in subs:
        subs.append(data)
        save_subs(subs)
    return jsonify({'ok': True, 'count': len(subs)})

@app.route('/test-push', methods=['POST'])
def test():
    subs = load_subs()
    for s in subs:
        send_push(s, 'Test - Scanner works!', 'If you got this, notifications are connected!', 'https://otc-app1.onrender.com')
    return jsonify({'sent': len(subs)})

@app.route('/scan-now')
def scan():
    items = fetch_sec() + fetch_globe()
    res = [{'title': t, 'score': score(t), 'url': u} for t, u in items[:15]]
    return jsonify(res)

threading.Thread(target=scanner_loop, daemon=True).start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
