import requests
import json
import sys

URL = 'http://127.0.0.1:8000/file_opportunities'

def main():
    try:
        r = requests.get(URL, timeout=15)
    except Exception as e:
        print('ERROR: request failed:', e)
        sys.exit(1)
    print('status', r.status_code)
    txt = r.text
    print('response length:', len(txt))
    try:
        j = r.json()
    except Exception as e:
        print('ERROR: json parse failed:', e)
        print(txt[:2000])
        sys.exit(1)
    if not isinstance(j, list):
        print('payload is not list, type=', type(j))
        print(json.dumps(j, indent=2)[:2000])
        return
    print('items', len(j))
    if len(j) == 0:
        print('no items')
        return
    print('first item keys:', list(j[0].keys()))
    print('first item sample:')
    print(json.dumps(j[0], indent=2)[:4000])

if __name__ == '__main__':
    main()
