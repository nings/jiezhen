"""
价格工具函数模块
提供价格处理相关的工具函数
"""


def round_price_to_tick(price: float, tick_size: float) -> str:
    """
    将价格调整为tick_size的整数倍

    Args:
        price: 原始价格
        tick_size: 最小价格变动单位

    Returns:
        调整后的价格字符串
    """
    # 计算 tick_size 的小数位数
    tick_decimals = len(f"{tick_size:.10f}".rstrip('0').split('.')[1]) if '.' in f"{tick_size:.10f}" else 0

    # 调整价格为 tick_size 的整数倍
    adjusted_price = round(price / tick_size) * tick_size

    return f"{adjusted_price:.{tick_decimals}f}"
