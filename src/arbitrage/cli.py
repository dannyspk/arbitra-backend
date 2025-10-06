"""Small CLI entrypoint for the arbitrage package."""
from __future__ import annotations

from . import __version__
from .exchanges.mock_exchange import MockExchange
from .scanner import find_opportunities
from .executor import Executor


def fetch_prices() -> dict:
    """Placeholder that would fetch prices from exchanges.
    Returns a dict mapping symbol -> price (floats).
    """
    # Placeholder data — replace with real HTTP calls / SDKs
    return {"BTC-USD": 50000.0, "ETH-USD": 3000.0}


def main() -> None:
    """Simple CLI that prints the package version and sample prices."""
    import argparse

    parser = argparse.ArgumentParser(description="arbitrage demo CLI")
    parser.add_argument("--scan", action="store_true", help="scan for opportunities using mock exchanges")
    parser.add_argument("--execute", action="store_true", help="execute the top opportunity (dry-run by default)")
    parser.add_argument("--amount", type=float, default=0.01, help="amount to trade")
    parser.add_argument("--dry-run", dest="dry_run", action="store_true", help="dry run when executing")
    parser.add_argument("--no-dry-run", dest="dry_run", action="store_false", help="perform real execution (mocked in demo)")
    parser.set_defaults(dry_run=True)

    args = parser.parse_args()

    if not args.scan:
        print(f"arbitrage v{__version__}")
        prices = fetch_prices()
        print("sample prices:")
        for sym, p in prices.items():
            print(f"  {sym}: {p}")
        return

    # create some mock exchanges with overlapping symbols
    ex1 = MockExchange("CEX-A", {"BTC-USD": 50010.0, "ETH-USD": 2995.0})
    ex2 = MockExchange("CEX-B", {"BTC-USD": 49900.0, "ETH-USD": 3010.0})
    ex3 = MockExchange("DEX-X", {"BTC-USD": 50050.0})

    exs = [ex1, ex2, ex3]
    opps = find_opportunities(exs, min_profit_pct=0.05)
    if not opps:
        print("No opportunities found")
        return

    print("Opportunities:")
    for o in opps:
        print(f"  {o.symbol} buy@{o.buy_exchange}:{o.buy_price} sell@{o.sell_exchange}:{o.sell_price} profit%={o.profit_pct:.3f}")

    if args.execute:
        executor = Executor(exs)
        top = opps[0]
        res = executor.execute(top, args.amount, dry_run=args.dry_run)
        print("Execution result:")
        print(res)


if __name__ == "__main__":
    main()
