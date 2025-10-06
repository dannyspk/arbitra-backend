# Quick smoke test for updated HTF gating in QuickScalpStrategy
from arbitrage.strategy import QuickScalpStrategy

# create strategy with tightened params for test
s = QuickScalpStrategy()
# create synthetic recent_closes: build 1440+ minutes of slowly falling HTF (to emulate 24h downtrend)
base = 10.0
recent = [base * (1 - i * 0.0001) for i in range(1500)]  # slight downward drift

# ensure momentum_window small positive in short-term by slightly increasing last few
for i in range(1494, 1500):
    recent[i] = recent[i] * 1.002  # small short-term bump

# call decide
dec = s.decide(price=recent[-1], recent_closes=recent, funding_rate=None, position=None)
print('decision:', dec)
