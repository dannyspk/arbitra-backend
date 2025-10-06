import urllib.request as req
import json

try:
    r = req.Request('https://yields.llama.fi/pools')
    r.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    
    with req.urlopen(r, timeout=10) as resp:
        data = json.loads(resp.read().decode('utf-8'))
    
    pools = data.get('data', [])
    print(f'Total pools fetched: {len(pools)}')
    
    # Filter for target protocols
    target_protocols = ['morpho-blue', 'aave-v3', 'compound-v3', 'venus', 'benqi', 'resolv']
    target_chains = ['Ethereum', 'BSC', 'Avalanche']
    
    filtered = []
    for p in pools:
        if p.get('stablecoin') == True and p.get('ilRisk') == 'no':
            project = p.get('project', '').lower()
            chain = p.get('chain', '')
            
            if any(proto in project for proto in target_protocols):
                if chain in target_chains:
                    apy = p.get('apy', 0)
                    tvl = p.get('tvlUsd', 0)
                    if apy > 3.0 and tvl > 1000000:
                        filtered.append(p)
    
    print(f'Filtered pools: {len(filtered)}')
    
    # Show top 10
    filtered.sort(key=lambda x: x.get('apy', 0), reverse=True)
    print('\nTop 10 pools:')
    for p in filtered[:10]:
        print(f"  {p.get('project')} - {p.get('symbol')} - {p.get('chain')} - APY: {p.get('apy', 0):.2f}% - TVL: ${p.get('tvlUsd', 0)/1e6:.1f}M")
        
except Exception as e:
    print(f'Error: {e}')
    import traceback
    traceback.print_exc()
