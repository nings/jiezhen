"""
振幅（Amplitude）指标计算
"""
from typing import List


def calculate_average_amplitude(klines: List[List], period: int = 60) -> float:
    """
    计算平均振幅

    Args:
        klines: K线数据列表，每个元素为 [时间, 开, 高, 低, 收, 成交量]
        period: 计算周期

    Returns:
        平均振幅百分比
    """
    amplitudes = []

    # 计算最近period根K线的振幅
    for i in range(len(klines) - period, len(klines)):
        high = float(klines[i][2])
        low = float(klines[i][3])
        close = float(klines[i][4])

        # 振幅 = (最高价 - 最低价) / 收盘价 * 100%
        amplitude = ((high - low) / close) * 100
        amplitudes.append(amplitude)

    # 计算平均振幅
    average_amplitude = sum(amplitudes) / len(amplitudes)
    return average_amplitude
