"""Live trading dashboard - tracks positions, signals, and P&L in real-time."""
from __future__ import annotations

import time
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
import threading


@dataclass
class Position:
    """Active position tracking."""
    symbol: str
    side: str  # 'long' or 'short'
    entry_price: float
    size: float
    entry_time: int  # timestamp ms
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    unrealized_pnl: float = 0.0
    unrealized_pnl_pct: float = 0.0
    market: str = 'spot'  # 'spot' or 'futures'
    is_live: bool = False  # True for live positions, False for test positions
    
    def update_pnl(self, current_price: float):
        """Update unrealized P&L based on current price."""
        if self.side == 'long':
            pnl = (current_price - self.entry_price) * self.size
            pnl_pct = ((current_price - self.entry_price) / self.entry_price) * 100
        else:  # short
            pnl = (self.entry_price - current_price) * self.size
            pnl_pct = ((self.entry_price - current_price) / self.entry_price) * 100
        
        self.unrealized_pnl = pnl
        self.unrealized_pnl_pct = pnl_pct


@dataclass
class Signal:
    """Trading signal record."""
    id: str
    timestamp: int
    symbol: str
    action: str  # 'open_long', 'open_short', 'close_long', 'close_short'
    price: float
    size: Optional[float]
    reason: str
    status: str = 'pending'  # 'pending', 'executed', 'failed'
    order_id: Optional[str] = None
    error: Optional[str] = None


@dataclass
class Trade:
    """Completed trade record."""
    symbol: str
    side: str
    entry_price: float
    exit_price: float
    size: float
    entry_time: int
    exit_time: int
    pnl: float
    pnl_pct: float
    reason: str  # 'tp', 'sl', 'manual'


class LiveDashboard:
    """Thread-safe dashboard for tracking live trading state."""
    
    def __init__(self):
        self._lock = threading.RLock()
        
        # Active positions by symbol
        self._positions: Dict[str, Position] = {}
        
        # Recent signals (keep last 100)
        self._signals: List[Signal] = []
        self._max_signals = 100
        
        # Completed trades (keep last 100)
        self._trades: List[Trade] = []
        self._max_trades = 100
        
        # Strategy status
        self._strategy_running = False
        self._strategy_mode = 'paper'
        self._strategy_symbol = None
        self._strategy_type = None  # 'bear' or 'bull'
        
        # Paper trading balance and fees
        self._test_balance: float = 500.0  # Starting test balance
        self._initial_balance: float = 500.0
        self._taker_fee_rate: float = 0.0005  # 0.05% (Binance Futures taker fee)
        self._maker_fee_rate: float = 0.0002  # 0.02% (Binance Futures maker fee)
        
        # Live trading fee tracking
        self._total_fees_paid: float = 0.0  # Track all fees paid on live trades
        
        # Statistics
        self._total_trades = 0
        self._winning_trades = 0
        self._total_pnl = 0.0
        self._start_time = None
    
    def start_strategy(self, symbol: str, mode: str, strategy_type: str):
        """Mark strategy as started."""
        with self._lock:
            self._strategy_running = True
            self._strategy_mode = mode
            self._strategy_symbol = symbol
            self._strategy_type = strategy_type
            if self._start_time is None:
                self._start_time = int(time.time() * 1000)
    
    def stop_strategy(self):
        """Mark strategy as stopped."""
        with self._lock:
            self._strategy_running = False
    
    def add_signal(self, signal: Signal):
        """Add a new trading signal."""
        with self._lock:
            self._signals.insert(0, signal)
            if len(self._signals) > self._max_signals:
                self._signals = self._signals[:self._max_signals]
    
    def update_signal_status(self, signal_id: str, status: str, order_id: Optional[str] = None, error: Optional[str] = None):
        """Update signal execution status."""
        with self._lock:
            for sig in self._signals:
                if sig.id == signal_id:
                    sig.status = status
                    if order_id:
                        sig.order_id = order_id
                    if error:
                        sig.error = error
                    break
    
    def open_position(self, position: Position):
        """Open a new position and deduct entry fee from test balance."""
        with self._lock:
            # Calculate entry fee (using taker fee for market orders)
            position_value = position.entry_price * position.size
            entry_fee = position_value * self._taker_fee_rate
            
            # Deduct fee from test balance
            self._test_balance -= entry_fee
            
            # Store position
            self._positions[position.symbol] = position
            
            print(f"[BALANCE] Position opened: {position.symbol} {position.side.upper()}")
            print(f"[BALANCE] Position value: ${position_value:.2f}, Entry fee: ${entry_fee:.2f}")
            print(f"[BALANCE] Test balance: ${self._test_balance:.2f}")
    
    def close_position(self, symbol: str, exit_price: float, reason: str = 'manual') -> Optional[Trade]:
        """Close a position, settle P&L, and deduct exit fee from test balance."""
        with self._lock:
            pos = self._positions.pop(symbol, None)
            if pos is None:
                return None
            
            # Calculate gross P&L
            if pos.side == 'long':
                gross_pnl = (exit_price - pos.entry_price) * pos.size
                pnl_pct = ((exit_price - pos.entry_price) / pos.entry_price) * 100
            else:
                gross_pnl = (pos.entry_price - exit_price) * pos.size
                pnl_pct = ((pos.entry_price - exit_price) / pos.entry_price) * 100
            
            # Calculate exit fee
            exit_value = exit_price * pos.size
            exit_fee = exit_value * self._taker_fee_rate
            
            # Net P&L after fees (entry fee was already deducted)
            net_pnl = gross_pnl - exit_fee
            
            # Settle P&L to test balance
            self._test_balance += gross_pnl  # Add gross P&L
            self._test_balance -= exit_fee    # Deduct exit fee
            
            print(f"[BALANCE] Position closed: {symbol} {pos.side.upper()}")
            print(f"[BALANCE] Gross P&L: ${gross_pnl:.2f}, Exit fee: ${exit_fee:.2f}, Net P&L: ${net_pnl:.2f}")
            print(f"[BALANCE] Test balance: ${self._test_balance:.2f}")
            
            # Create trade record
            trade = Trade(
                symbol=symbol,
                side=pos.side,
                entry_price=pos.entry_price,
                exit_price=exit_price,
                size=pos.size,
                entry_time=pos.entry_time,
                exit_time=int(time.time() * 1000),
                pnl=net_pnl,  # Store net P&L after fees
                pnl_pct=pnl_pct,
                reason=reason
            )
            
            # Update statistics
            self._total_trades += 1
            if net_pnl > 0:
                self._winning_trades += 1
            self._total_pnl += net_pnl
            
            # Store trade
            self._trades.insert(0, trade)
            if len(self._trades) > self._max_trades:
                self._trades = self._trades[:self._max_trades]
            
            print(f"[LiveDashboard] Trade recorded: {symbol} {pos.side} entry=${pos.entry_price:.2f} exit=${exit_price:.2f} P&L=${net_pnl:.2f} ({pnl_pct:.2f}%) reason={reason}")
            print(f"[LiveDashboard] Total trades: {self._total_trades}, Stored trades: {len(self._trades)}")
            
            return trade
    
    def update_position_pnl(self, symbol: str, current_price: float):
        """Update position P&L with current market price."""
        with self._lock:
            pos = self._positions.get(symbol)
            if pos:
                pos.update_pnl(current_price)
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """Get position by symbol."""
        with self._lock:
            return self._positions.get(symbol)
    
    def get_all_positions(self) -> List[Position]:
        """Get all active positions."""
        with self._lock:
            return list(self._positions.values())
    
    def get_recent_signals(self, limit: int = 20) -> List[Signal]:
        """Get recent signals."""
        with self._lock:
            return self._signals[:limit]
    
    def get_recent_trades(self, limit: int = 20) -> List[Trade]:
        """Get recent completed trades."""
        with self._lock:
            return self._trades[:limit]
    
    def get_statistics(self) -> Dict:
        """Get trading statistics."""
        with self._lock:
            win_rate = (self._winning_trades / self._total_trades * 100) if self._total_trades > 0 else 0.0
            
            # Calculate unrealized P&L from open positions
            unrealized_pnl = sum(pos.unrealized_pnl for pos in self._positions.values())
            
            return {
                'total_trades': self._total_trades,
                'winning_trades': self._winning_trades,
                'losing_trades': self._total_trades - self._winning_trades,
                'win_rate': win_rate,
                'realized_pnl': self._total_pnl,
                'unrealized_pnl': unrealized_pnl,
                'total_pnl': self._total_pnl + unrealized_pnl,
                'active_positions': len(self._positions),
                'uptime_ms': int(time.time() * 1000) - self._start_time if self._start_time else 0
            }
    
    def add_fee_paid(self, fee_amount: float):
        """Track fees paid on live trades."""
        with self._lock:
            self._total_fees_paid += fee_amount
            print(f"[FEES] Fee tracked: ${fee_amount:.2f}, Total fees: ${self._total_fees_paid:.2f}")
    
    def get_total_fees_paid(self) -> float:
        """Get total fees paid on live trades."""
        with self._lock:
            return self._total_fees_paid
    
    def get_total_unrealized_pnl(self, live_only: bool = False) -> float:
        """Get total unrealized PNL from open positions.
        
        Args:
            live_only: If True, only include live positions. If False, only test positions.
        """
        with self._lock:
            if live_only:
                return sum(pos.unrealized_pnl for pos in self._positions.values() if getattr(pos, 'is_live', False))
            else:
                return sum(pos.unrealized_pnl for pos in self._positions.values() if not getattr(pos, 'is_live', False))
    
    def calculate_net_balance(self, wallet_balance: float, live_only: bool = True) -> Dict:
        """
        Calculate comprehensive balance including fees and PNL.
        
        Args:
            wallet_balance: Current Binance wallet balance
            live_only: If True, only include live positions. If False, only test positions.
            
        Returns:
            Dict with wallet, unrealized PNL, fees, and net balance
        """
        with self._lock:
            unrealized_pnl = sum(
                pos.unrealized_pnl 
                for pos in self._positions.values() 
                if getattr(pos, 'is_live', False) == live_only
            )
            total_fees = self._total_fees_paid
            
            # Net balance = wallet + unrealized PNL - fees paid
            # (Realized PNL is already in wallet, fees already deducted from wallet)
            net_balance = wallet_balance + unrealized_pnl
            
            return {
                'wallet_balance': wallet_balance,
                'unrealized_pnl': unrealized_pnl,
                'total_fees_paid': total_fees,
                'net_balance': net_balance,
                'realized_pnl': self._total_pnl
            }
    
    def get_full_state(self) -> Dict:
        """Get complete dashboard state."""
        with self._lock:
            return {
                'strategy': {
                    'running': self._strategy_running,
                    'mode': self._strategy_mode,
                    'symbol': self._strategy_symbol,
                    'type': self._strategy_type,
                },
                'positions': [asdict(p) for p in self._positions.values()],
                'signals': [asdict(s) for s in self._signals[:20]],
                'trades': [asdict(t) for t in self._trades[:20]],
                'statistics': self.get_statistics(),
                'balance': {
                    'current': self._test_balance,
                    'initial': self._initial_balance,
                    'pnl': self._test_balance - self._initial_balance,
                    'pnl_pct': ((self._test_balance - self._initial_balance) / self._initial_balance * 100) if self._initial_balance > 0 else 0.0
                },
                'timestamp': int(time.time() * 1000)
            }
    
    def get_balance(self) -> float:
        """Get current test balance."""
        with self._lock:
            return self._test_balance
    
    def reset_balance(self, amount: float = 500.0):
        """Reset test balance to specified amount."""
        with self._lock:
            self._test_balance = amount
            self._initial_balance = amount
            print(f"[BALANCE] Test balance reset to ${amount:.2f}")
    
    def reset(self):
        """Reset all dashboard data (useful for testing)."""
        with self._lock:
            self._positions.clear()
            self._signals.clear()
            self._trades.clear()
            self._total_trades = 0
            self._winning_trades = 0
            self._total_pnl = 0.0
            self._start_time = None
            self._strategy_running = False
            self._test_balance = self._initial_balance  # Reset to initial balance
            print(f"[BALANCE] Dashboard reset, balance: ${self._test_balance:.2f}")


# Global singleton instance
_dashboard = LiveDashboard()


def get_dashboard() -> LiveDashboard:
    """Get the global dashboard instance."""
    return _dashboard
