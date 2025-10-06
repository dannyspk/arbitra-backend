import requests, json
base = 'http://127.0.0.1:8000'
paths = ['/debug/feeder_status','/debug/feeder_depths?feeder_name=binance','/debug/feeder_depths?feeder_name=kucoin']
for p in paths:
    try:
        r = requests.get(base + p, timeout=5)
        print('\nGET', p, '->', r.status_code)
        try:
            j = r.json()
            s = json.dumps(j, indent=2)
            print(s[:8000])
        except Exception as e:
            print('json error', e)
    except Exception as e:
        print('ERR', p, e)
