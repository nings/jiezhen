"""
工具函数模块
提供通用的工具函数
"""
import logging
import requests
from typing import Dict, Any, Optional
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path


def setup_logger(
    name: str,
    log_file: str,
    level: int = logging.INFO,
    console_output: bool = True
) -> logging.Logger:
    """
    配置日志记录器

    Args:
        name: 日志记录器名称
        log_file: 日志文件路径
        level: 日志级别
        console_output: 是否输出到控制台

    Returns:
        配置好的日志记录器
    """
    # 创建日志目录
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(level)

    # 移除已有的处理器（避免重复）
    logger.handlers.clear()

    # 文件处理器（每日轮转）
    file_handler = TimedRotatingFileHandler(
        log_file,
        when='midnight',
        interval=1,
        backupCount=7,
        encoding='utf-8'
    )
    file_handler.suffix = "%Y-%m-%d"
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # 控制台处理器
    if console_output:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger


class FeishuNotifier:
    """飞书通知器"""

    def __init__(self, webhook_url: str, enabled: bool = True):
        """
        初始化飞书通知器

        Args:
            webhook_url: 飞书机器人Webhook URL
            enabled: 是否启用通知
        """
        self.webhook_url = webhook_url
        self.enabled = enabled and bool(webhook_url)
        self.logger = logging.getLogger(__name__)

    def send_text(self, message: str) -> bool:
        """
        发送文本消息

        Args:
            message: 消息内容

        Returns:
            是否发送成功
        """
        if not self.enabled:
            return False

        try:
            headers = {'Content-Type': 'application/json'}
            data = {
                "msg_type": "text",
                "content": {"text": message}
            }
            response = requests.post(
                self.webhook_url,
                headers=headers,
                json=data,
                timeout=10
            )

            if response.status_code == 200:
                self.logger.info("飞书通知发送成功")
                return True
            else:
                self.logger.error(f"飞书通知发送失败: {response.text}")
                return False

        except Exception as e:
            self.logger.error(f"飞书通知发送异常: {e}")
            return False

    def send_card(
        self,
        title: str,
        content: Dict[str, Any],
        color: str = "blue"
    ) -> bool:
        """
        发送卡片消息

        Args:
            title: 卡片标题
            content: 卡片内容
            color: 卡片颜色

        Returns:
            是否发送成功
        """
        if not self.enabled:
            return False

        try:
            headers = {'Content-Type': 'application/json'}
            data = {
                "msg_type": "interactive",
                "card": {
                    "config": {"wide_screen_mode": True},
                    "header": {
                        "title": {"tag": "plain_text", "content": title},
                        "template": color
                    },
                    "elements": [content]
                }
            }
            response = requests.post(
                self.webhook_url,
                headers=headers,
                json=data,
                timeout=10
            )

            if response.status_code == 200:
                self.logger.info("飞书卡片通知发送成功")
                return True
            else:
                self.logger.error(f"飞书卡片通知发送失败: {response.text}")
                return False

        except Exception as e:
            self.logger.error(f"飞书卡片通知发送异常: {e}")
            return False

    def notify_error(self, error_message: str, inst_id: str = None):
        """
        发送错误通知

        Args:
            error_message: 错误消息
            inst_id: 交易对ID（可选）
        """
        prefix = f"[{inst_id}] " if inst_id else ""
        message = f"⚠️ {prefix}错误: {error_message}"
        self.send_text(message)

    def notify_order(
        self,
        inst_id: str,
        side: str,
        price: float,
        amount: float,
        success: bool = True
    ):
        """
        发送订单通知

        Args:
            inst_id: 交易对ID
            side: 方向
            price: 价格
            amount: 金额
            success: 是否成功
        """
        if success:
            emoji = "✅"
            status = "成功"
        else:
            emoji = "❌"
            status = "失败"

        message = (
            f"{emoji} 订单{status}\n"
            f"交易对: {inst_id}\n"
            f"方向: {side.upper()}\n"
            f"价格: {price:.6f}\n"
            f"金额: {amount:.2f} USDT"
        )
        self.send_text(message)

    def notify_daily_report(self, report: str):
        """
        发送每日报告

        Args:
            report: 报告内容
        """
        message = f"📊 每日交易报告\n\n{report}"
        self.send_text(message)

    def notify_risk_alert(self, alert_message: str, level: str = "warning"):
        """
        发送风险警告

        Args:
            alert_message: 警告消息
            level: 警告级别
        """
        emoji_map = {
            'info': 'ℹ️',
            'warning': '⚠️',
            'critical': '🚨'
        }
        emoji = emoji_map.get(level, '⚠️')
        message = f"{emoji} 风险警告\n\n{alert_message}"
        self.send_text(message)


def format_number(value: float, decimals: int = 2) -> str:
    """
    格式化数字

    Args:
        value: 数值
        decimals: 小数位数

    Returns:
        格式化后的字符串
    """
    return f"{value:.{decimals}f}"


def format_percentage(value: float, decimals: int = 2) -> str:
    """
    格式化百分比

    Args:
        value: 数值
        decimals: 小数位数

    Returns:
        格式化后的百分比字符串
    """
    return f"{value:.{decimals}f}%"


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """
    安全除法（避免除零错误）

    Args:
        numerator: 分子
        denominator: 分母
        default: 默认值（当分母为0时）

    Returns:
        除法结果或默认值
    """
    if denominator == 0:
        return default
    return numerator / denominator


def validate_inst_id(inst_id: str) -> bool:
    """
    验证交易对ID格式

    Args:
        inst_id: 交易对ID

    Returns:
        是否有效
    """
    # OKX永续合约格式：XXX-USDT-SWAP
    parts = inst_id.split('-')
    return len(parts) == 3 and parts[1] == 'USDT' and parts[2] == 'SWAP'


def parse_kline_data(kline: list) -> Dict[str, float]:
    """
    解析K线数据

    Args:
        kline: K线数组 [timestamp, open, high, low, close, volume, ...]

    Returns:
        解析后的字典
    """
    return {
        'timestamp': int(kline[0]),
        'open': float(kline[1]),
        'high': float(kline[2]),
        'low': float(kline[3]),
        'close': float(kline[4]),
        'volume': float(kline[5]) if len(kline) > 5 else 0,
    }


class RateLimiter:
    """简单的速率限制器"""

    def __init__(self, max_calls: int, time_window: float):
        """
        初始化速率限制器

        Args:
            max_calls: 时间窗口内最大调用次数
            time_window: 时间窗口（秒）
        """
        self.max_calls = max_calls
        self.time_window = time_window
        self.calls = []

    def can_call(self) -> bool:
        """
        检查是否可以调用

        Returns:
            是否可以调用
        """
        import time
        now = time.time()

        # 移除过期的调用记录
        self.calls = [call_time for call_time in self.calls
                      if now - call_time < self.time_window]

        return len(self.calls) < self.max_calls

    def record_call(self):
        """记录一次调用"""
        import time
        self.calls.append(time.time())

    def wait_if_needed(self):
        """如果需要，等待直到可以调用"""
        import time
        while not self.can_call():
            time.sleep(0.1)
        self.record_call()
