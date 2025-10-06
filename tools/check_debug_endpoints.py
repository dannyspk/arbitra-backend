import requests, json
base = 'http://127.0.0.1:8000'
for path in ['/debug/feeder_status', '/debug/feeder_depths?feeder_name=mexc', '/debug/ccxt_status', '/logs']:
    try:
        r = requests.get(base + path, timeout=5)
        print('\nGET', path, '->', r.status_code)
        try:
            print(json.dumps(r.json(), indent=2)[:4000])
        except Exception as e:
            print('json error', e)
    except Exception as e:
        print('\nERR', path, e)
