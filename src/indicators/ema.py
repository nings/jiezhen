"""
EMA (Exponential Moving Average) 指标计算
"""
import pandas as pd
from typing import List


def calculate_ema(data: List[float], period: int) -> float:
    """
    使用 pandas 计算 EMA

    Args:
        data: 收盘价列表
        period: EMA 周期

    Returns:
        EMA 值
    """
    if len(data) < period:
        raise ValueError(f"数据长度 {len(data)} 小于EMA周期 {period}")

    df = pd.Series(data)
    ema = df.ewm(span=period, adjust=False).mean()
    return ema.iloc[-1]  # 返回最后一个 EMA 值
