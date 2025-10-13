"""
Test orderbook depth checking with specific price targets
"""
import json
from urllib import request as _req

def test_orderbook_depth():
    """Test the orderbook depth logic"""
    
    # Fetch a real orderbook from Binance for BTC
    url = 'https://api.binance.com/api/v3/depth?symbol=BTCUSDT&limit=20'
    req = _req.Request(url)
    req.add_header('User-Agent', 'Mozilla/5.0')
    
    with _req.urlopen(req, timeout=5) as r:
        data = json.load(r)
    
    bids = data.get('bids', [])
    asks = data.get('asks', [])
    
    print("\n" + "="*80)
    print("Orderbook Depth Test for BTCUSDT")
    print("="*80)
    
    print("\nTop 5 Bids (prices where people want to BUY):")
    for i, bid in enumerate(bids[:5]):
        price = float(bid[0])
        quantity = float(bid[1])
        depth_usd = price * quantity
        print(f"  {i+1}. ${price:,.2f} x {quantity:.4f} BTC = ${depth_usd:,.2f}")
    
    print("\nTop 5 Asks (prices where people want to SELL):")
    for i, ask in enumerate(asks[:5]):
        price = float(ask[0])
        quantity = float(ask[1])
        depth_usd = price * quantity
        print(f"  {i+1}. ${price:,.2f} x {quantity:.4f} BTC = ${depth_usd:,.2f}")
    
    # Simulate arbitrage scenario
    best_bid = float(bids[0][0])
    best_ask = float(asks[0][0])
    
    print(f"\nBest Bid: ${best_bid:,.2f}")
    print(f"Best Ask: ${best_ask:,.2f}")
    print(f"Spread: {((best_ask - best_bid) / best_bid) * 100:.4f}%")
    
    # Test scenario: Exchange A has price $100,000, Exchange B has $102,000
    # Can we buy $50 worth at Exchange A (check asks)?
    # Can we sell $50 worth at Exchange B (check bids)?
    
    target_buy_price = best_ask
    target_sell_price = best_bid
    
    print(f"\n{'='*80}")
    print("Testing: Can we buy $50 worth at ${:,.2f}?".format(target_buy_price))
    print("="*80)
    
    buy_depth_usd = 0
    price_tolerance = target_buy_price * 1.005  # 0.5% tolerance
    for ask in asks[:10]:
        price = float(ask[0])
        quantity = float(ask[1])
        if price <= price_tolerance:
            depth_at_level = price * quantity
            buy_depth_usd += depth_at_level
            print(f"  Ask at ${price:,.2f}: {quantity:.6f} BTC = ${depth_at_level:,.2f} (cumulative: ${buy_depth_usd:,.2f})")
            if buy_depth_usd >= 50:
                print(f"  ✓ Reached $50 threshold!")
                break
        else:
            print(f"  X Price ${price:,.2f} exceeds tolerance ${price_tolerance:,.2f}, stopping")
            break
    
    print(f"\n{'='*80}")
    print("Testing: Can we sell $50 worth at ${:,.2f}?".format(target_sell_price))
    print("="*80)
    
    sell_depth_usd = 0
    price_tolerance = target_sell_price * 0.995  # 0.5% tolerance
    for bid in bids[:10]:
        price = float(bid[0])
        quantity = float(bid[1])
        if price >= price_tolerance:
            depth_at_level = price * quantity
            sell_depth_usd += depth_at_level
            print(f"  Bid at ${price:,.2f}: {quantity:.6f} BTC = ${depth_at_level:,.2f} (cumulative: ${sell_depth_usd:,.2f})")
            if sell_depth_usd >= 50:
                print(f"  ✓ Reached $50 threshold!")
                break
        else:
            print(f"  X Price ${price:,.2f} below tolerance ${price_tolerance:,.2f}, stopping")
            break
    
    print(f"\n{'='*80}")
    print("Summary")
    print("="*80)
    print(f"Buy depth at ${target_buy_price:,.2f}: ${buy_depth_usd:,.2f} {'✓ OK' if buy_depth_usd >= 50 else '✗ INSUFFICIENT'}")
    print(f"Sell depth at ${target_sell_price:,.2f}: ${sell_depth_usd:,.2f} {'✓ OK' if sell_depth_usd >= 50 else '✗ INSUFFICIENT'}")

if __name__ == "__main__":
    test_orderbook_depth()
