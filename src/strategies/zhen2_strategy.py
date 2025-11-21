"""
Zhen2策略（版本2）
使用 (average_amplitude + price_atr_ratio) / 2 计算挂单距离
更侧重ATR的影响
"""
from src.strategies.base_strategy import BaseStrategy


class Zhen2Strategy(BaseStrategy):
    """Zhen2策略 - 使用平均值方法"""

    def calculate_target_value(self, average_amplitude: float, price_atr_ratio: float,
                               value_multiplier: float) -> float:
        """
        计算目标价值 - 使用振幅和ATR比值的平均值

        Args:
            average_amplitude: 平均振幅
            price_atr_ratio: 价格/ATR比值
            value_multiplier: 价值乘数

        Returns:
            目标价值
        """
        selected_value = (average_amplitude + price_atr_ratio) / 2 * value_multiplier
        return selected_value
