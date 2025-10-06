#!/usr/bin/env python3
import urllib.request, json, datetime, time

url = 'http://127.0.0.1:8000/logs'
headers = {'Content-Type': 'application/json'}

def post(payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req) as r:
        return json.load(r)

# post 3 synthetic feature_extractor alerts
for i in range(1, 4):
    payload = {
        'ts': datetime.datetime.now().isoformat(),
        'level': 'warning',
        'src': 'feature_extractor',
        'text': f'UI test alert #{i}',
        'alerts': [{'pair': 'BTC/USDT', 'side': 'long', 'size_usd': 1000 * i}]
    }
    try:
        res = post(payload)
        print('POST OK:', res.get('entry', {}).get('ts'), '-', res.get('entry', {}).get('text'))
    except Exception as e:
        print('POST ERR:', e)
    time.sleep(0.2)

# post 5 hotcoins broadcast messages
for i in range(1, 6):
    payload = {
        'ts': (datetime.datetime.now() - datetime.timedelta(seconds=i)).isoformat(),
        'text': f'hotcoins: broadcast {i} items'
    }
    try:
        res = post(payload)
        print('HOT POST OK:', res.get('entry', {}).get('ts'), '-', res.get('entry', {}).get('text'))
    except Exception as e:
        print('HOT POST ERR:', e)
    time.sleep(0.15)

# fetch logs and count recent alerts and hotcoins in last 5 minutes
req = urllib.request.Request(url + '?limit=200')
with urllib.request.urlopen(req) as r:
    j = json.load(r)
logs = j.get('logs', [])
print('---GET /logs count:', j.get('count'), '---')

now_ts = datetime.datetime.now().timestamp()
cutoff = now_ts - 5 * 60
c_alerts = 0
c_hot = 0
recent_alerts = []
for l in logs:
    ts = l.get('ts')
    if not ts:
        continue
    try:
        t = datetime.datetime.fromisoformat(ts).timestamp()
    except Exception:
        try:
            t = float(ts) / 1000.0
        except Exception:
            continue
    if t < cutoff:
        continue
    txt = str(l.get('text', '')).lower()
    if (l.get('src') in ('feature_extractor', 'feature-extractor')) and (l.get('alerts') or 'alerts:' in txt):
        c_alerts += 1
        recent_alerts.append(l)
    if 'hotcoins: broadcast' in txt:
        c_hot += 1

print('recent alerts in last 5m:', c_alerts)
print('hotcoins in last 5m:', c_hot)
print('recent_alerts sample:')
for a in recent_alerts[-5:]:
    print('-', a.get('ts'), a.get('text'))
