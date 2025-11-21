"""
通知模块
负责发送各种通知（飞书等）
"""
import requests
from typing import Optional
from src.utils.logger import Logger

logger = Logger.get_logger(__name__)


class NotificationManager:
    """通知管理器类"""

    def __init__(self, feishu_webhook: str = ''):
        """
        初始化通知管理器

        Args:
            feishu_webhook: 飞书webhook地址
        """
        self.feishu_webhook = feishu_webhook

    def send_feishu(self, message: str) -> bool:
        """
        发送飞书通知

        Args:
            message: 通知消息内容

        Returns:
            是否发送成功
        """
        if not self.feishu_webhook:
            logger.warning("飞书webhook未配置，跳过通知发送")
            return False

        try:
            headers = {'Content-Type': 'application/json'}
            data = {
                "msg_type": "text",
                "content": {"text": message}
            }
            response = requests.post(
                self.feishu_webhook,
                headers=headers,
                json=data,
                timeout=10
            )

            if response.status_code == 200:
                logger.info("飞书通知发送成功")
                return True
            else:
                logger.error(f"飞书通知发送失败: {response.text}")
                return False

        except Exception as e:
            logger.error(f"发送飞书通知时出错: {e}")
            return False

    def send_error(self, inst_id: str, error: Exception) -> None:
        """
        发送错误通知

        Args:
            inst_id: 交易对ID
            error: 错误对象
        """
        error_message = f"交易对 {inst_id} 发生错误: {str(error)}"
        logger.error(error_message)
        self.send_feishu(error_message)

    def send_order_notification(self, inst_id: str, side: str, price: float, message: str) -> None:
        """
        发送订单通知

        Args:
            inst_id: 交易对ID
            side: 方向（buy/sell）
            price: 价格
            message: 消息内容
        """
        notification = f"{inst_id} {side} @ {price}: {message}"
        logger.info(notification)
        self.send_feishu(notification)
