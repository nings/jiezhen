"""
订单管理模块
负责订单的下单、取消等操作
"""
from typing import Dict, Any
from src.core.api_client import OKXClient
from src.core.instrument_manager import InstrumentManager
from src.utils.logger import Logger
from src.utils.notification import NotificationManager
from src.utils.price_utils import round_price_to_tick

logger = Logger.get_logger(__name__)


class OrderManager:
    """订单管理器"""

    def __init__(self, client: OKXClient, instrument_manager: InstrumentManager,
                 notification_manager: NotificationManager, leverage: int = 10):
        """
        初始化订单管理器

        Args:
            client: OKX客户端
            instrument_manager: 交易品种管理器
            notification_manager: 通知管理器
            leverage: 杠杆倍数
        """
        self.client = client
        self.instrument_manager = instrument_manager
        self.notification_manager = notification_manager
        self.leverage = leverage

    def cancel_all_orders(self, inst_id: str) -> None:
        """
        取消指定交易对的所有订单

        Args:
            inst_id: 交易对ID
        """
        try:
            open_orders = self.client.get_order_list(inst_id=inst_id, state='live')
            if 'data' in open_orders:
                order_ids = [order['ordId'] for order in open_orders['data']]
                for ord_id in order_ids:
                    self.client.cancel_order(instId=inst_id, ordId=ord_id)
                logger.info(f"{inst_id} 挂单取消成功，共取消 {len(order_ids)} 个订单")
        except Exception as e:
            logger.error(f"取消订单失败: {e}")

    def set_leverage(self, inst_id: str, pos_side: str = None) -> bool:
        """
        设置杠杆

        Args:
            inst_id: 交易对ID
            pos_side: 持仓方向（long/short）

        Returns:
            是否设置成功
        """
        try:
            response = self.client.set_leverage(
                inst_id=inst_id,
                lever=self.leverage,
                mgn_mode='isolated',
                pos_side=pos_side
            )

            if response['code'] == '0':
                logger.info(f"Leverage set to {self.leverage}x for {inst_id} with mgnMode: isolated")
                return True
            else:
                logger.error(f"Failed to set leverage: {response['msg']}")
                return False

        except Exception as e:
            logger.error(f"Error setting leverage: {e}")
            return False

    def place_order(self, inst_id: str, price: float, amount_usdt: float, side: str) -> bool:
        """
        下单

        Args:
            inst_id: 交易对ID
            price: 价格
            amount_usdt: 金额（USDT）
            side: 方向（buy/sell）

        Returns:
            是否下单成功
        """
        try:
            # 检查交易品种是否存在
            if not self.instrument_manager.has_instrument(inst_id):
                logger.error(f"Instrument {inst_id} not found in instrument info dictionary")
                return False

            # 获取tick_size并调整价格
            tick_size = self.instrument_manager.get_tick_size(inst_id)
            adjusted_price = round_price_to_tick(price, tick_size)

            # 转换金额为合约张数
            response = self.client.convert_contract_coin(
                inst_id=inst_id,
                sz=str(amount_usdt),
                px=str(adjusted_price),
                type='1',
                unit='usdt',
                op_type='open'
            )

            if response['code'] == '0':
                sz = response['data'][0]['sz']
                if float(sz) > 0:
                    # 设置杠杆
                    pos_side = 'long' if side == 'buy' else 'short'
                    self.set_leverage(inst_id, pos_side=pos_side)

                    # 下单
                    order_result = self.client.place_order(
                        inst_id=inst_id,
                        td_mode='isolated',
                        pos_side=pos_side,
                        side=side,
                        ord_type='limit',
                        sz=sz,
                        px=str(adjusted_price)
                    )

                    logger.info(f"Order placed: {order_result}")
                    return True
                else:
                    logger.info(f"{inst_id} 计算出的合约张数太小，无法下单。")
                    return False
            else:
                error_msg = f"{inst_id} 转换失败: {response['msg']}"
                logger.info(error_msg)
                self.notification_manager.send_feishu(error_msg)
                return False

        except Exception as e:
            logger.error(f"下单失败: {e}")
            return False
