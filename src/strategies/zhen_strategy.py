"""
Zhen策略（版本1）
使用 min(average_amplitude, price_atr_ratio) 计算挂单距离
"""
from src.strategies.base_strategy import BaseStrategy


class ZhenStrategy(BaseStrategy):
    """Zhen策略 - 使用最小值方法"""

    def calculate_target_value(self, average_amplitude: float, price_atr_ratio: float,
                               value_multiplier: float) -> float:
        """
        计算目标价值 - 使用振幅和ATR比值的最小值

        Args:
            average_amplitude: 平均振幅
            price_atr_ratio: 价格/ATR比值
            value_multiplier: 价值乘数

        Returns:
            目标价值
        """
        selected_value = min(average_amplitude, price_atr_ratio) * value_multiplier
        selected_value = max(selected_value, 0.8)  # 最小值限制
        return selected_value
