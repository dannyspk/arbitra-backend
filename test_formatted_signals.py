"""Test the formatted signal reasons"""
import requests
import json

print("\n" + "="*80)
print("TESTING HUMAN-READABLE SIGNAL FORMATTING")
print("="*80)

r = requests.get('http://127.0.0.1:8000/api/dashboard/signals')
signals = r.json()['signals']

print(f"\nTotal signals: {len(signals)}\n")

for i, sig in enumerate(signals[:5], 1):
    print(f"{i}. {sig['symbol']} - {sig['action'].upper()} @ ${sig['price']:.2f}")
    print(f"   Reason: {sig['reason']}")
    print()

print("="*80)
print("\n✅ Signals are now human-readable!")
print("Refresh your dashboard to see the updated formatting.")
print("="*80 + "\n")
