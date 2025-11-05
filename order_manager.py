"""
订单管理模块
处理订单的下单、撤单、查询等操作，带重试机制和错误处理
"""
import time
import logging
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass
from functools import wraps

import okx.Trade_api as TradeAPI
import okx.Public_api as PublicAPI
import okx.Market_api as MarketAPI
import okx.Account_api as AccountAPI

logger = logging.getLogger(__name__)


@dataclass
class RetryConfig:
    """重试配置"""
    max_retries: int = 3
    base_delay: float = 1.0  # 基础延迟（秒）
    exponential_backoff: bool = True  # 是否使用指数退避


def retry_on_error(retry_config: RetryConfig = None):
    """
    错误重试装饰器

    Args:
        retry_config: 重试配置
    """
    if retry_config is None:
        retry_config = RetryConfig()

    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(retry_config.max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < retry_config.max_retries:
                        delay = retry_config.base_delay
                        if retry_config.exponential_backoff:
                            delay *= (2 ** attempt)

                        logger.warning(
                            f"{func.__name__} 失败 (尝试 {attempt + 1}/{retry_config.max_retries + 1}): {e}. "
                            f"{delay:.1f}秒后重试..."
                        )
                        time.sleep(delay)
                    else:
                        logger.error(
                            f"{func.__name__} 在 {retry_config.max_retries + 1} 次尝试后仍然失败: {e}"
                        )

            raise last_exception

        return wrapper
    return decorator


class OrderManager:
    """订单管理器"""

    def __init__(
        self,
        trade_api: TradeAPI.TradeAPI,
        market_api: MarketAPI.MarketAPI,
        public_api: PublicAPI.PublicAPI,
        account_api: AccountAPI.AccountAPI,
        instrument_info: Dict[str, Dict],
        retry_config: RetryConfig = None
    ):
        """
        初始化订单管理器

        Args:
            trade_api: 交易API
            market_api: 市场API
            public_api: 公开API
            account_api: 账户API
            instrument_info: 合约信息字典
            retry_config: 重试配置
        """
        self.trade_api = trade_api
        self.market_api = market_api
        self.public_api = public_api
        self.account_api = account_api
        self.instrument_info = instrument_info
        self.retry_config = retry_config or RetryConfig()

    @retry_on_error(RetryConfig(max_retries=3))
    def get_mark_price(self, inst_id: str) -> float:
        """
        获取标记价格（带重试）

        Args:
            inst_id: 交易对ID

        Returns:
            标记价格

        Raises:
            ValueError: 响应格式错误或缺少数据
        """
        response = self.market_api.get_ticker(inst_id)
        if 'data' in response and len(response['data']) > 0:
            last_price = response['data'][0]['last']
            return float(last_price)
        else:
            raise ValueError(f"{inst_id}: 获取价格失败或响应格式错误")

    @retry_on_error(RetryConfig(max_retries=3))
    def get_historical_klines(
        self,
        inst_id: str,
        bar: str = '1m',
        limit: int = 241
    ) -> list:
        """
        获取历史K线数据（带重试）

        Args:
            inst_id: 交易对ID
            bar: K线周期
            limit: 数量

        Returns:
            K线数据列表

        Raises:
            ValueError: 响应格式错误或缺少数据
        """
        response = self.market_api.get_candlesticks(inst_id, bar=bar, limit=limit)
        if 'data' in response and len(response['data']) > 0:
            return response['data']
        else:
            raise ValueError(f"{inst_id}: 获取K线数据失败或响应格式错误")

    def round_price_to_tick(self, inst_id: str, price: float) -> str:
        """
        将价格调整到tick_size的整数倍

        Args:
            inst_id: 交易对ID
            price: 原始价格

        Returns:
            调整后的价格字符串
        """
        if inst_id not in self.instrument_info:
            logger.error(f"合约 {inst_id} 的信息未找到")
            return f"{price:.8f}"

        tick_size = float(self.instrument_info[inst_id]['tickSz'])

        # 计算 tick_size 的小数位数
        tick_decimals = len(f"{tick_size:.10f}".rstrip('0').split('.')[1]) \
            if '.' in f"{tick_size:.10f}" else 0

        # 调整价格为 tick_size 的整数倍
        adjusted_price = round(price / tick_size) * tick_size
        return f"{adjusted_price:.{tick_decimals}f}"

    @retry_on_error(RetryConfig(max_retries=2))
    def convert_usdt_to_contracts(
        self,
        inst_id: str,
        amount_usdt: float,
        price: float
    ) -> str:
        """
        将USDT金额转换为合约张数（带重试）

        Args:
            inst_id: 交易对ID
            amount_usdt: USDT金额
            price: 价格

        Returns:
            合约张数（字符串）

        Raises:
            ValueError: 转换失败
        """
        adjusted_price = self.round_price_to_tick(inst_id, price)

        response = self.public_api.convert_contract_coin(
            type='1',
            instId=inst_id,
            sz=str(amount_usdt),
            px=adjusted_price,
            unit='usdt',
            opType='open'
        )

        if response['code'] == '0':
            sz = response['data'][0]['sz']
            if float(sz) > 0:
                return sz
            else:
                raise ValueError(f"{inst_id}: 计算出的合约张数太小")
        else:
            raise ValueError(f"{inst_id}: 转换失败 - {response.get('msg', '未知错误')}")

    @retry_on_error(RetryConfig(max_retries=2))
    def set_leverage(
        self,
        inst_id: str,
        leverage: int,
        mgn_mode: str = 'isolated',
        pos_side: Optional[str] = None
    ) -> bool:
        """
        设置杠杆倍数（带重试）

        Args:
            inst_id: 交易对ID
            leverage: 杠杆倍数
            mgn_mode: 保证金模式
            pos_side: 持仓方向（isolated模式必需）

        Returns:
            是否成功
        """
        body = {
            "instId": inst_id,
            "lever": str(leverage),
            "mgnMode": mgn_mode
        }

        if mgn_mode == 'isolated' and pos_side:
            body["posSide"] = pos_side

        response = self.account_api.set_leverage(**body)

        if response['code'] == '0':
            logger.info(f"{inst_id}: 杠杆设置为 {leverage}x (模式: {mgn_mode})")
            return True
        else:
            logger.error(f"{inst_id}: 设置杠杆失败 - {response.get('msg', '未知错误')}")
            return False

    @retry_on_error(RetryConfig(max_retries=2))
    def place_limit_order(
        self,
        inst_id: str,
        side: str,
        price: float,
        amount_usdt: float,
        leverage: int,
        td_mode: str = 'isolated'
    ) -> Optional[Dict[str, Any]]:
        """
        下限价单（带重试）

        Args:
            inst_id: 交易对ID
            side: 方向（'buy'/'sell'）
            price: 价格
            amount_usdt: 金额（USDT）
            leverage: 杠杆倍数
            td_mode: 交易模式

        Returns:
            订单结果（成功）或 None（失败）
        """
        try:
            # 转换USDT为合约张数
            sz = self.convert_usdt_to_contracts(inst_id, amount_usdt, price)

            # 设置杠杆
            pos_side = 'long' if side == 'buy' else 'short'
            self.set_leverage(inst_id, leverage, mgn_mode=td_mode, pos_side=pos_side)

            # 调整价格
            adjusted_price = self.round_price_to_tick(inst_id, price)

            # 下单
            order_result = self.trade_api.place_order(
                instId=inst_id,
                tdMode=td_mode,
                posSide=pos_side,
                side=side,
                ordType='limit',
                sz=sz,
                px=adjusted_price
            )

            if order_result['code'] == '0':
                logger.info(
                    f"{inst_id}: 订单已下 [{side.upper()}] "
                    f"价格: {adjusted_price}, 数量: {sz}, "
                    f"金额: {amount_usdt} USDT"
                )
                return order_result
            else:
                logger.error(
                    f"{inst_id}: 下单失败 - {order_result.get('msg', '未知错误')}"
                )
                return None

        except Exception as e:
            logger.error(f"{inst_id}: 下单异常 - {e}")
            raise

    @retry_on_error(RetryConfig(max_retries=2))
    def cancel_order(self, inst_id: str, order_id: str) -> bool:
        """
        撤销单个订单（带重试）

        Args:
            inst_id: 交易对ID
            order_id: 订单ID

        Returns:
            是否成功
        """
        try:
            response = self.trade_api.cancel_order(instId=inst_id, ordId=order_id)
            if response['code'] == '0':
                logger.info(f"{inst_id}: 订单 {order_id} 已撤销")
                return True
            else:
                logger.warning(
                    f"{inst_id}: 撤销订单 {order_id} 失败 - "
                    f"{response.get('msg', '未知错误')}"
                )
                return False
        except Exception as e:
            logger.error(f"{inst_id}: 撤销订单 {order_id} 异常 - {e}")
            return False

    def cancel_all_orders(self, inst_id: str) -> int:
        """
        撤销交易对的所有未成交订单

        Args:
            inst_id: 交易对ID

        Returns:
            撤销的订单数量
        """
        try:
            open_orders = self.trade_api.get_order_list(instId=inst_id, state='live')

            if 'data' not in open_orders:
                logger.warning(f"{inst_id}: 获取订单列表失败")
                return 0

            order_ids = [order['ordId'] for order in open_orders['data']]

            if not order_ids:
                logger.info(f"{inst_id}: 无未成交订单")
                return 0

            cancelled_count = 0
            for ord_id in order_ids:
                if self.cancel_order(inst_id, ord_id):
                    cancelled_count += 1

            logger.info(f"{inst_id}: 已撤销 {cancelled_count}/{len(order_ids)} 个订单")
            return cancelled_count

        except Exception as e:
            logger.error(f"{inst_id}: 撤销所有订单异常 - {e}")
            return 0

    def get_open_orders_count(self, inst_id: str) -> int:
        """
        获取未成交订单数量

        Args:
            inst_id: 交易对ID

        Returns:
            未成交订单数量
        """
        try:
            open_orders = self.trade_api.get_order_list(instId=inst_id, state='live')
            if 'data' in open_orders:
                return len(open_orders['data'])
            return 0
        except Exception as e:
            logger.error(f"{inst_id}: 获取未成交订单数量异常 - {e}")
            return 0

    def get_positions(self, inst_id: str = None) -> list:
        """
        获取持仓信息

        Args:
            inst_id: 交易对ID（可选，不指定则获取所有持仓）

        Returns:
            持仓列表
        """
        try:
            params = {}
            if inst_id:
                params['instId'] = inst_id

            response = self.account_api.get_positions(**params)
            if 'data' in response:
                return response['data']
            return []
        except Exception as e:
            logger.error(f"获取持仓信息异常 - {e}")
            return []
