"""
策略基类
定义策略接口和公共方法
"""
from abc import ABC, abstractmethod
from typing import Dict, Any
from src.core.api_client import OKXClient
from src.core.instrument_manager import InstrumentManager
from src.trading.order_manager import OrderManager
from src.utils.logger import Logger
from src.utils.notification import NotificationManager
from src.indicators.atr import calculate_atr
from src.indicators.ema import calculate_ema
from src.indicators.amplitude import calculate_average_amplitude

logger = Logger.get_logger(__name__)


class BaseStrategy(ABC):
    """策略基类"""

    def __init__(self, client: OKXClient, instrument_manager: InstrumentManager,
                 order_manager: OrderManager, notification_manager: NotificationManager):
        """
        初始化策略

        Args:
            client: OKX客户端
            instrument_manager: 交易品种管理器
            order_manager: 订单管理器
            notification_manager: 通知管理器
        """
        self.client = client
        self.instrument_manager = instrument_manager
        self.order_manager = order_manager
        self.notification_manager = notification_manager

    @abstractmethod
    def calculate_target_value(self, average_amplitude: float, price_atr_ratio: float,
                               value_multiplier: float) -> float:
        """
        计算目标价值（抽象方法，由子类实现）

        Args:
            average_amplitude: 平均振幅
            price_atr_ratio: 价格/ATR比值
            value_multiplier: 价值乘数

        Returns:
            目标价值
        """
        pass

    def process_pair(self, inst_id: str, pair_config: Dict[str, Any]) -> None:
        """
        处理单个交易对

        Args:
            inst_id: 交易对ID
            pair_config: 交易对配置
        """
        try:
            # 获取当前价格
            mark_price = self.client.get_mark_price(inst_id)

            # 获取K线数据
            klines = self.client.get_candlesticks(inst_id)

            # 提取收盘价数据用于计算 EMA
            close_prices = [float(kline[4]) for kline in klines[::-1]]  # K线中的收盘价，顺序要新的在最后

            # 计算 EMA 并判断趋势
            ema_value = pair_config.get('ema', 240)

            # 如果ema值为0 不区分方向，两头都挂单
            if ema_value == 0:
                is_bullish_trend = True
                is_bearish_trend = True
            else:
                ema = calculate_ema(close_prices, period=ema_value)
                logger.info(f"{inst_id} EMA{ema_value}: {ema:.6f}, 当前价格: {mark_price:.6f}")

                # 判断趋势：多头趋势或空头趋势
                is_bullish_trend = close_prices[-1] > ema  # 收盘价在 EMA 之上
                is_bearish_trend = close_prices[-1] < ema  # 收盘价在 EMA 之下

            # 计算 ATR
            atr = calculate_atr(klines)
            price_atr_ratio = (mark_price / atr) / 100
            logger.info(f"{inst_id} ATR: {atr}, 当前价格/ATR比值: {price_atr_ratio:.3f}")

            # 计算平均振幅
            average_amplitude = calculate_average_amplitude(klines)
            logger.info(f"{inst_id} 平均振幅: {average_amplitude:.2f}%")

            # 获取配置参数
            value_multiplier = pair_config.get('value_multiplier', 2)

            # 计算目标价值（由子类实现）
            selected_value = self.calculate_target_value(
                average_amplitude, price_atr_ratio, value_multiplier
            )

            # 计算目标价格
            long_price_factor = 1 - selected_value / 100
            short_price_factor = 1 + selected_value / 100

            long_amount_usdt = pair_config.get('long_amount_usdt', 20)
            short_amount_usdt = pair_config.get('short_amount_usdt', 20)

            target_price_long = mark_price * long_price_factor
            target_price_short = mark_price * short_price_factor

            logger.info(f"{inst_id} Long target price: {target_price_long:.6f}, "
                       f"Short target price: {target_price_short:.6f}")

            # 取消所有订单
            self.order_manager.cancel_all_orders(inst_id)

            # 判断趋势后决定是否挂单
            if is_bullish_trend:
                logger.info(f"{inst_id} 当前为多头趋势，允许挂多单")
                self.order_manager.place_order(inst_id, target_price_long, long_amount_usdt, 'buy')
            else:
                logger.info(f"{inst_id} 当前非多头趋势，跳过多单挂单")

            if is_bearish_trend:
                logger.info(f"{inst_id} 当前为空头趋势，允许挂空单")
                self.order_manager.place_order(inst_id, target_price_short, short_amount_usdt, 'sell')
            else:
                logger.info(f"{inst_id} 当前非空头趋势，跳过空单挂单")

        except Exception as e:
            error_message = f'Error processing {inst_id}: {e}'
            logger.error(error_message)
            self.notification_manager.send_feishu(error_message)
