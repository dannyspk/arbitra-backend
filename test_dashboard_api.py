"""Test dashboard API to verify signals are being returned"""
import requests
import json

# Test both endpoints
print("="*80)
print("Testing /api/dashboard?mode=test")
print("="*80)

r = requests.get('http://127.0.0.1:8000/api/dashboard?mode=test')
data = r.json()

signals = data.get('signals', [])
print(f"\n✅ Total signals: {len(signals)}")

if signals:
    print("\n📊 Recent signals:")
    for i, sig in enumerate(signals[:5], 1):
        print(f"  {i}. {sig['symbol']} - {sig['action'].upper()} @ ${sig['price']:.2f}")
        print(f"     Timestamp: {sig['timestamp']}")
        print(f"     Status: {sig['status']}")
        print(f"     Reason: {sig['reason'][:80]}...")
        print()
else:
    print("\n❌ No signals found!")

print("\n" + "="*80)
print("Testing /api/dashboard/signals")
print("="*80)

r2 = requests.get('http://127.0.0.1:8000/api/dashboard/signals')
signals2 = r2.json().get('signals', [])
print(f"\n✅ Total signals: {len(signals2)}")

print("\n" + "="*80)
print(f"Frontend should display {len(signals)} signals!")
print("If dashboard shows 'No signals yet', try:")
print("  1. Hard refresh browser (Ctrl+Shift+R)")
print("  2. Clear browser cache")
print("  3. Check browser console for errors")
print("="*80)
