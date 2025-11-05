"""
交易策略模块
封装不同的交易策略逻辑
"""
from typing import Tuple, Dict, Any
from dataclasses import dataclass
from abc import ABC, abstractmethod
import logging

from indicators import TechnicalIndicators, TrendAnalyzer

logger = logging.getLogger(__name__)


@dataclass
class SignalResult:
    """信号结果"""
    should_long: bool  # 是否应该做多
    should_short: bool  # 是否应该做空
    long_price: float  # 做多价格
    short_price: float  # 做空价格
    distance_percentage: float  # 下单距离（百分比）
    metadata: Dict[str, Any] = None  # 额外的元数据

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class BaseStrategy(ABC):
    """策略基类"""

    def __init__(self, indicator_calculator: TechnicalIndicators):
        """
        初始化策略

        Args:
            indicator_calculator: 技术指标计算器
        """
        self.indicator_calculator = indicator_calculator
        self.trend_analyzer = TrendAnalyzer()

    @abstractmethod
    def generate_signal(
        self,
        inst_id: str,
        current_price: float,
        klines: list,
        config: Dict[str, Any]
    ) -> SignalResult:
        """
        生成交易信号

        Args:
            inst_id: 交易对ID
            current_price: 当前价格
            klines: K线数据
            config: 策略配置

        Returns:
            信号结果
        """
        pass


class PinBarStrategy(BaseStrategy):
    """
    接针策略（Pin Bar Strategy）
    基于 EMA + ATR 的趋势跟随和波动性自适应策略
    """

    def __init__(
        self,
        indicator_calculator: TechnicalIndicators,
        min_distance_percentage: float = 0.8
    ):
        """
        初始化接针策略

        Args:
            indicator_calculator: 技术指标计算器
            min_distance_percentage: 最小下单距离（百分比）
        """
        super().__init__(indicator_calculator)
        self.min_distance_percentage = min_distance_percentage

    def generate_signal(
        self,
        inst_id: str,
        current_price: float,
        klines: list,
        config: Dict[str, Any]
    ) -> SignalResult:
        """
        生成交易信号

        策略逻辑：
        1. 计算 EMA 判断趋势方向
        2. 计算 ATR 和平均振幅衡量波动性
        3. 基于波动性计算下单距离
        4. 根据趋势决定做多/做空

        Args:
            inst_id: 交易对ID
            current_price: 当前价格
            klines: K线数据（时间倒序）
            config: 策略配置
                - ema_period: EMA周期（默认240）
                - ema_enabled: 是否启用EMA（默认True）
                - value_multiplier: 距离倍数（默认2）
                - atr_period: ATR周期（默认60）
                - amplitude_period: 振幅周期（默认60）

        Returns:
            信号结果
        """
        # 提取配置
        ema_period = config.get('ema_period', 240)
        ema_enabled = config.get('ema_enabled', True)
        value_multiplier = config.get('value_multiplier', 2.0)
        atr_period = config.get('atr_period', 60)
        amplitude_period = config.get('amplitude_period', 60)

        # 提取收盘价（需要时间正序）
        close_prices = [float(kline[4]) for kline in klines[::-1]]

        # 计算趋势
        is_bullish = True
        is_bearish = True
        ema_value = 0.0

        if ema_enabled and ema_period > 0:
            ema_value = self.indicator_calculator.calculate_ema(
                inst_id=inst_id,
                close_prices=close_prices,
                period=ema_period
            )
            is_bullish, is_bearish = self.trend_analyzer.analyze_trend(
                current_price=current_price,
                ema=ema_value,
                ema_enabled=True
            )
            logger.info(f"{inst_id} EMA({ema_period}): {ema_value:.6f}, 当前价格: {current_price:.6f}")
        else:
            logger.info(f"{inst_id} EMA未启用，允许双向交易")

        # 计算 ATR
        atr = self.indicator_calculator.calculate_atr(
            inst_id=inst_id,
            klines=klines,
            period=atr_period
        )
        price_atr_ratio = self.indicator_calculator.calculate_price_atr_ratio(
            price=current_price,
            atr=atr
        )
        logger.info(f"{inst_id} ATR: {atr:.6f}, 价格/ATR比值: {price_atr_ratio:.3f}")

        # 计算平均振幅
        average_amplitude = self.indicator_calculator.calculate_average_amplitude(
            inst_id=inst_id,
            klines=klines,
            period=amplitude_period
        )
        logger.info(f"{inst_id} 平均振幅: {average_amplitude:.2f}%")

        # 计算下单距离（使用平均值，更侧重ATR）
        distance_percentage = self._calculate_order_distance(
            average_amplitude=average_amplitude,
            price_atr_ratio=price_atr_ratio,
            value_multiplier=value_multiplier
        )

        logger.info(f"{inst_id} 下单距离: {distance_percentage:.2f}%")

        # 计算目标价格
        long_price = current_price * (1 - distance_percentage / 100)
        short_price = current_price * (1 + distance_percentage / 100)

        logger.info(
            f"{inst_id} 多单目标价: {long_price:.6f}, "
            f"空单目标价: {short_price:.6f}"
        )

        return SignalResult(
            should_long=is_bullish,
            should_short=is_bearish,
            long_price=long_price,
            short_price=short_price,
            distance_percentage=distance_percentage,
            metadata={
                'ema': ema_value,
                'atr': atr,
                'average_amplitude': average_amplitude,
                'price_atr_ratio': price_atr_ratio,
                'trend': 'bullish' if is_bullish and not is_bearish else 'bearish' if is_bearish and not is_bullish else 'neutral'
            }
        )

    def _calculate_order_distance(
        self,
        average_amplitude: float,
        price_atr_ratio: float,
        value_multiplier: float
    ) -> float:
        """
        计算下单距离

        Args:
            average_amplitude: 平均振幅
            price_atr_ratio: 价格/ATR比值
            value_multiplier: 距离倍数

        Returns:
            下单距离（百分比）
        """
        # 使用振幅和ATR的平均值，更侧重ATR
        distance = (average_amplitude + price_atr_ratio) / 2 * value_multiplier

        # 确保不低于最小距离
        return max(distance, self.min_distance_percentage)


class ConservativePinBarStrategy(BaseStrategy):
    """
    保守型接针策略
    使用最小值而非平均值，更保守的下单策略
    """

    def __init__(
        self,
        indicator_calculator: TechnicalIndicators,
        min_distance_percentage: float = 0.8
    ):
        """
        初始化保守型接针策略

        Args:
            indicator_calculator: 技术指标计算器
            min_distance_percentage: 最小下单距离（百分比）
        """
        super().__init__(indicator_calculator)
        self.min_distance_percentage = min_distance_percentage

    def generate_signal(
        self,
        inst_id: str,
        current_price: float,
        klines: list,
        config: Dict[str, Any]
    ) -> SignalResult:
        """
        生成交易信号（保守型）

        与标准策略的区别：
        - 使用 min(振幅, ATR比值) 而非平均值
        - 下单距离更小，更接近当前价格
        """
        # 提取配置
        ema_period = config.get('ema_period', 240)
        ema_enabled = config.get('ema_enabled', True)
        value_multiplier = config.get('value_multiplier', 2.0)
        atr_period = config.get('atr_period', 60)
        amplitude_period = config.get('amplitude_period', 60)

        # 提取收盘价
        close_prices = [float(kline[4]) for kline in klines[::-1]]

        # 计算趋势
        is_bullish = True
        is_bearish = True
        ema_value = 0.0

        if ema_enabled and ema_period > 0:
            ema_value = self.indicator_calculator.calculate_ema(
                inst_id=inst_id,
                close_prices=close_prices,
                period=ema_period
            )
            is_bullish, is_bearish = self.trend_analyzer.analyze_trend(
                current_price=current_price,
                ema=ema_value,
                ema_enabled=True
            )
            logger.info(f"{inst_id} [保守] EMA({ema_period}): {ema_value:.6f}")

        # 计算 ATR 和振幅
        atr = self.indicator_calculator.calculate_atr(
            inst_id=inst_id,
            klines=klines,
            period=atr_period
        )
        price_atr_ratio = self.indicator_calculator.calculate_price_atr_ratio(
            price=current_price,
            atr=atr
        )

        average_amplitude = self.indicator_calculator.calculate_average_amplitude(
            inst_id=inst_id,
            klines=klines,
            period=amplitude_period
        )

        # 计算下单距离（使用最小值，更保守）
        distance_percentage = self._calculate_order_distance(
            average_amplitude=average_amplitude,
            price_atr_ratio=price_atr_ratio,
            value_multiplier=value_multiplier
        )

        logger.info(f"{inst_id} [保守] 下单距离: {distance_percentage:.2f}%")

        # 计算目标价格
        long_price = current_price * (1 - distance_percentage / 100)
        short_price = current_price * (1 + distance_percentage / 100)

        return SignalResult(
            should_long=is_bullish,
            should_short=is_bearish,
            long_price=long_price,
            short_price=short_price,
            distance_percentage=distance_percentage,
            metadata={
                'ema': ema_value,
                'atr': atr,
                'average_amplitude': average_amplitude,
                'price_atr_ratio': price_atr_ratio,
                'strategy_type': 'conservative'
            }
        )

    def _calculate_order_distance(
        self,
        average_amplitude: float,
        price_atr_ratio: float,
        value_multiplier: float
    ) -> float:
        """
        计算下单距离（保守型）

        使用最小值而非平均值
        """
        # 使用最小值，更保守
        distance = min(average_amplitude, price_atr_ratio) * value_multiplier

        # 确保不低于最小距离
        return max(distance, self.min_distance_percentage)


class StrategyFactory:
    """策略工厂"""

    @staticmethod
    def create_strategy(
        strategy_type: str,
        indicator_calculator: TechnicalIndicators,
        **kwargs
    ) -> BaseStrategy:
        """
        创建策略实例

        Args:
            strategy_type: 策略类型（'pinbar', 'conservative'）
            indicator_calculator: 技术指标计算器
            **kwargs: 额外参数

        Returns:
            策略实例

        Raises:
            ValueError: 不支持的策略类型
        """
        if strategy_type == 'pinbar':
            return PinBarStrategy(indicator_calculator, **kwargs)
        elif strategy_type == 'conservative':
            return ConservativePinBarStrategy(indicator_calculator, **kwargs)
        else:
            raise ValueError(f"不支持的策略类型: {strategy_type}")
