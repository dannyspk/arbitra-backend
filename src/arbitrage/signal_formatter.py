"""Helper to format technical signal reasons into human-readable text"""

def format_signal_reason(raw_reason: str) -> str:
    """
    Convert technical signal reasons to human-readable format.
    
    Input: "slope=0.0068,funding=-0.000686,vol=0.009845361107779269,trend=up,sr_low=None,sr_high=6.971,atr=0.012883262905588416,mom=0.006942824630091431"
    Output: "Uptrend detected: +0.68% slope, momentum +0.69%, high resistance at $6.97"
    """
    if not raw_reason or '=' not in raw_reason:
        return raw_reason
    
    # Parse key-value pairs
    parts = {}
    for item in raw_reason.split(','):
        if '=' in item:
            key, value = item.split('=', 1)
            parts[key.strip()] = value.strip()
    
    # Build human-readable message
    message_parts = []
    
    # Trend
    trend = parts.get('trend', '')
    if trend == 'up':
        message_parts.append("📈 Uptrend")
    elif trend == 'down':
        message_parts.append("📉 Downtrend")
    elif trend == 'neutral':
        message_parts.append("➡️ Neutral")
    
    # Slope (price change rate)
    slope = parts.get('slope')
    if slope:
        try:
            slope_pct = float(slope) * 100
            if abs(slope_pct) >= 0.5:
                direction = "rising" if slope_pct > 0 else "falling"
                message_parts.append(f"{direction} {abs(slope_pct):.1f}%")
        except:
            pass
    
    # Momentum
    mom = parts.get('mom')
    if mom:
        try:
            mom_pct = float(mom) * 100
            if abs(mom_pct) >= 0.3:
                message_parts.append(f"momentum {mom_pct:+.1f}%")
        except:
            pass
    
    # Support/Resistance
    sr_low = parts.get('sr_low')
    sr_high = parts.get('sr_high')
    
    if sr_low and sr_low != 'None':
        try:
            message_parts.append(f"support ${float(sr_low):.2f}")
        except:
            pass
    
    if sr_high and sr_high != 'None':
        try:
            message_parts.append(f"resistance ${float(sr_high):.2f}")
        except:
            pass
    
    # Volatility
    vol = parts.get('vol')
    if vol:
        try:
            vol_val = float(vol)
            if vol_val > 0.01:
                message_parts.append(f"high volatility ({vol_val:.1%})")
            elif vol_val > 0.005:
                message_parts.append(f"moderate volatility")
        except:
            pass
    
    # Funding rate (for futures)
    funding = parts.get('funding')
    if funding:
        try:
            funding_val = float(funding)
            if abs(funding_val) > 0.0005:
                if funding_val > 0:
                    message_parts.append("longs paying shorts")
                else:
                    message_parts.append("shorts paying longs")
        except:
            pass
    
    # Combine all parts
    if message_parts:
        return " • ".join(message_parts)
    else:
        return raw_reason
