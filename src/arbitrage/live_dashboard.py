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
        """Open a new position."""
        with self._lock:
            self._positions[position.symbol] = position
    
    def close_position(self, symbol: str, exit_price: float, reason: str = 'manual') -> Optional[Trade]:
        """Close a position and record the trade."""
        with self._lock:
            pos = self._positions.pop(symbol, None)
            if pos is None:
                return None
            
            # Calculate final P&L
            if pos.side == 'long':
                pnl = (exit_price - pos.entry_price) * pos.size
                pnl_pct = ((exit_price - pos.entry_price) / pos.entry_price) * 100
            else:
                pnl = (pos.entry_price - exit_price) * pos.size
                pnl_pct = ((pos.entry_price - exit_price) / pos.entry_price) * 100
            
            # Create trade record
            trade = Trade(
                symbol=symbol,
                side=pos.side,
                entry_price=pos.entry_price,
                exit_price=exit_price,
                size=pos.size,
                entry_time=pos.entry_time,
                exit_time=int(time.time() * 1000),
                pnl=pnl,
                pnl_pct=pnl_pct,
                reason=reason
            )
            
            # Update statistics
            self._total_trades += 1
            if pnl > 0:
                self._winning_trades += 1
            self._total_pnl += pnl
            
            # Store trade
            self._trades.insert(0, trade)
            if len(self._trades) > self._max_trades:
                self._trades = self._trades[:self._max_trades]
            
            print(f"[LiveDashboard] Trade recorded: {symbol} {pos.side} entry=${pos.entry_price:.2f} exit=${exit_price:.2f} P&L=${pnl:.2f} ({pnl_pct:.2f}%) reason={reason}")
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
                'timestamp': int(time.time() * 1000)
            }
    
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


# Global singleton instance
_dashboard = LiveDashboard()


def get_dashboard() -> LiveDashboard:
    """Get the global dashboard instance."""
    return _dashboard
