import urllib.request as req
import json

try:
    r = req.Request('https://yields.llama.fi/pools')
    r.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    
    with req.urlopen(r, timeout=10) as resp:
        data = json.loads(resp.read().decode('utf-8'))
    
    pools = data.get('data', [])
    
    # Find the REUSDC pool
    for p in pools:
        symbol = p.get('symbol', '')
        if 'REUSDC' in symbol and 'morpho' in p.get('project', '').lower():
            print(f"Found REUSDC pool:")
            print(f"  Pool ID: {p.get('pool')}")
            print(f"  Symbol: {p.get('symbol')}")
            print(f"  Project: {p.get('project')}")
            print(f"  Chain: {p.get('chain')}")
            print(f"  APY: {p.get('apy', 0):.2f}%")
            print(f"  APY Base: {p.get('apyBase', 0):.2f}%")
            print(f"  APY Reward: {p.get('apyReward', 0):.2f}%")
            print(f"  APY Mean 30d: {p.get('apyMean30d', 0):.2f}%")
            print(f"  TVL: ${p.get('tvlUsd', 0):,.0f}")
            print(f"  Pool Meta: {p.get('poolMeta')}")
            print(f"  IL Risk: {p.get('ilRisk')}")
            print(f"  Stablecoin: {p.get('stablecoin')}")
            print(f"  Exposure: {p.get('exposure')}")
            print(f"  Predictions: {p.get('predictions')}")
            print(f"\nFull pool data:")
            print(json.dumps(p, indent=2))
            break
        
except Exception as e:
    print(f'Error: {e}')
    import traceback
    traceback.print_exc()
