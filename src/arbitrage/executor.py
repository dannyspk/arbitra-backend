from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import time
from typing import Dict, List, Optional

from .scanner import Opportunity


class Executor:
    def __init__(self, exchanges: List[object]):
        # map name -> exchange
        self.exchanges = {ex.name: ex for ex in exchanges}

    def execute(self, opp: Opportunity, amount: float, dry_run: bool = True) -> dict:
        """Execute the arbitrage opportunity.

        - opp: Opportunity
        - amount: size to trade (in base units for the symbol)
        - dry_run: if True, simulate and return what would happen without placing orders

        Returns a dict with details including order ids when executed.
        """
        buy_ex = self.exchanges.get(opp.buy_exchange)
        sell_ex = self.exchanges.get(opp.sell_exchange)
        if buy_ex is None or sell_ex is None:
            raise ValueError("Exchange for opportunity not available")

        result = {
            "opportunity": opp,
            "amount": amount,
            "buy_order": None,
            "sell_order": None,
            "dry_run": dry_run,
        }

        if dry_run:
            result["buy_order"] = {"action": "buy", "exchange": buy_ex.name, "symbol": opp.symbol, "price": opp.buy_price, "amount": amount}
            result["sell_order"] = {"action": "sell", "exchange": sell_ex.name, "symbol": opp.symbol, "price": opp.sell_price, "amount": amount}
            return result

        # Place buy then sell (very naive — real implementations need atomicity, hedging)
        buy_id = buy_ex.place_order(opp.symbol, "buy", amount)
        sell_id = sell_ex.place_order(opp.symbol, "sell", amount)
        result["buy_order"] = buy_id
        result["sell_order"] = sell_id
        return result


@dataclass
class Position:
    symbol: str
    direction: str  # 'long' or 'short'
    entry_price: float
    size: float  # notional in quote currency (USDT)
    qty: float  # base asset quantity
    entry_time: float
    pnl: float = 0.0
    exit_price: Optional[float] = None
    exit_time: Optional[float] = None


class DryRunExecutor:
    """A simple dry-run executor for backtests and strategy dry-runs.

    - Tracks a single open position per symbol.
    - Computes PnL on exit using provided exit price.
    - Applies configurable fee model and simple slippage.
    - Enforces minimum notional and rounds notional to a granularity to avoid tiny remnants.
    """

    def __init__(self, fee_rate: float = 0.0004, entry_fee_rate: Optional[float] = None, exit_fee_rate: Optional[float] = None, min_notional: float = 0.01, round_to: float = 0.01, slippage_bps: float = 0.0, max_partial_reduces: int = 100):
        self.active: Dict[str, Position] = {}
        self.closed: list[Position] = []
        # backward-compatible single fee_rate; if entry/exit provided, they override
        self.fee_rate = fee_rate
        self.entry_fee_rate = entry_fee_rate if entry_fee_rate is not None else fee_rate
        self.exit_fee_rate = exit_fee_rate if exit_fee_rate is not None else fee_rate
        self.min_notional = min_notional
        self.round_to = round_to
        # slippage in basis points (e.g., 5 bps => 0.0005)
        self.slippage_bps = slippage_bps
        # cap how many partial reduce operations are allowed per position before forcing exit
        self.max_partial_reduces = int(max_partial_reduces or 0)
        # track reduce counts per symbol
        self._reduce_counts: Dict[str, int] = {}

    def _round_notional(self, notional: float) -> float:
        if notional is None:
            return 0.0
        if self.round_to and self.round_to > 0:
            return max(self.min_notional, round(notional / self.round_to) * self.round_to)
        return max(self.min_notional, notional)

    def _apply_slippage(self, price: float, direction: str) -> float:
        # for simplicity: slippage is adverse to the trader
        slip = price * self.slippage_bps
        if direction == "long":
            return price + slip
        else:
            return price - slip

    def step(self, symbol: str, price: float, decision) -> Optional[dict]:
        act = getattr(decision, "action", None)
        if act is None and isinstance(decision, dict):
            act = decision.get("action")

        if act is None:
            return None

        if act == "enter":
            if symbol in self.active:
                return {"status": "noop", "reason": "already_in_position"}
            direction = getattr(decision, "direction", None) or decision.get("direction")
            raw_size = float(getattr(decision, "size", None) or decision.get("size", 0))
            size = self._round_notional(raw_size)
            if size < self.min_notional:
                return {"status": "noop", "reason": "notional_below_minimum", "size": size}
            # apply slippage to entry price
            exec_price = self._apply_slippage(price, direction)
            qty = size / exec_price if exec_price > 0 else 0.0
            pos = Position(
                symbol=symbol,
                direction=direction,
                entry_price=exec_price,
                size=size,
                qty=qty,
                entry_time=time.time(),
            )
            self.active[symbol] = pos
            # initialize reduce counter
            self._reduce_counts[symbol] = 0
            return {"status": "entered", "position": deepcopy(pos), "exec_price": exec_price}

        if act == "reduce":
            frac = getattr(decision, "fraction", None)
            if frac is None and isinstance(decision, dict):
                frac = decision.get("fraction")
            if frac is None:
                return {"status": "noop", "reason": "missing_fraction"}
            if symbol not in self.active:
                return {"status": "noop", "reason": "no_position_to_reduce"}
            pos = self.active[symbol]
            # increment partial-reduce counter and force an exit if too many reduces happened
            self._reduce_counts[symbol] = self._reduce_counts.get(symbol, 0) + 1
            if self.max_partial_reduces and self._reduce_counts.get(symbol, 0) > self.max_partial_reduces:
                # treat as forced exit to avoid many micro-reduces
                pos = self.active.pop(symbol)
                exit_price = self._apply_slippage(price, "short" if pos.direction == "long" else "long")
                if pos.direction == "long":
                    gross = pos.qty * (exit_price - pos.entry_price)
                else:
                    gross = pos.qty * (pos.entry_price - exit_price)
                # Only charge exit-side fee on forced exit here; entry fee should
                # have been applied at entry by the caller/backtest. Avoid double
                # counting the entry fee when finalizing a position.
                fees = (pos.qty * exit_price) * self.exit_fee_rate
                pos.pnl = pos.pnl + (gross - fees)
                pos.exit_price = exit_price
                pos.exit_time = time.time()
                self.closed.append(pos)
                # cleanup counter
                self._reduce_counts.pop(symbol, None)
                return {"status": "force_exit_due_to_reduce_cap", "position": deepcopy(pos)}
            # compute qty to close and realized pnl on that portion (apply slippage and exit fee)
            close_qty = pos.qty * frac
            # use adverse slippage for exit side
            exit_price = self._apply_slippage(price, "short" if pos.direction == "long" else "long")
            if pos.direction == "long":
                gross = close_qty * (exit_price - pos.entry_price)
            else:
                gross = close_qty * (pos.entry_price - exit_price)
            # For partial reduces only charge the exit-side fee for the portion
            # being closed; assume any entry-side fee was already accounted for.
            fees = (close_qty * exit_price) * self.exit_fee_rate
            realized = gross - fees
            pos.qty -= close_qty
            pos.size = pos.qty * pos.entry_price
            pos.pnl += realized
            # if fully closed as a result, finalize
            if pos.qty <= 1e-12:
                pos.exit_price = exit_price
                pos.exit_time = time.time()
                self.closed.append(pos)
                del self.active[symbol]
                # cleanup counter
                self._reduce_counts.pop(symbol, None)
                return {"status": "reduced_and_closed", "realized": realized, "position": deepcopy(pos)}
            return {"status": "reduced", "realized": realized, "remaining": deepcopy(pos)}

        if act == "exit":
            if symbol not in self.active:
                return {"status": "noop", "reason": "no_position"}
            pos = self.active.pop(symbol)
            exit_price = self._apply_slippage(price, "short" if pos.direction == "long" else "long")
            if pos.direction == "long":
                gross = pos.qty * (exit_price - pos.entry_price)
            else:
                gross = pos.qty * (pos.entry_price - exit_price)
            # On a normal exit only charge the exit-side fee; do not re-charge
            # the entry fee which would duplicate costs if the backtest already
            # deducted it at entry.
            fees = (pos.qty * exit_price) * self.exit_fee_rate
            pos.pnl = pos.pnl + (gross - fees)
            pos.exit_price = exit_price
            pos.exit_time = time.time()
            self.closed.append(pos)
            # cleanup reduce counter
            self._reduce_counts.pop(symbol, None)
            return {"status": "exited", "position": deepcopy(pos)}

        return {"status": "noop", "reason": "unknown_action"}

    def liquidate_all(self, price_map: Dict[str, float]) -> list:
        results = []
        for sym in list(self.active.keys()):
            price = price_map.get(sym)
            if price is None:
                continue
            results.append(self.step(sym, price, {"action": "exit"}))
        return results

    def get_active(self) -> Dict[str, Position]:
        return self.active
