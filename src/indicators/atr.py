"""
ATR (Average True Range) 指标计算
"""
from typing import List


def calculate_atr(klines: List[List], period: int = 60) -> float:
    """
    计算平均真实波幅（ATR）

    Args:
        klines: K线数据列表，每个元素为 [时间, 开, 高, 低, 收, 成交量]
        period: 计算周期

    Returns:
        ATR值
    """
    trs = []
    for i in range(1, len(klines)):
        high = float(klines[i][2])
        low = float(klines[i][3])
        prev_close = float(klines[i - 1][4])

        # 计算真实波幅 TR
        tr = max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close)
        )
        trs.append(tr)

    # 计算ATR（最近period个TR的平均值）
    atr = sum(trs[-period:]) / period
    return atr
