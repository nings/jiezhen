"""
配置文件加载器
负责加载和管理项目配置
"""
import json
import os
from typing import Dict, Any


class ConfigLoader:
    """配置加载器类"""

    def __init__(self, config_path: str = 'config.json'):
        """
        初始化配置加载器

        Args:
            config_path: 配置文件路径
        """
        self.config_path = config_path
        self._config = None
        self.load_config()

    def load_config(self) -> Dict[str, Any]:
        """
        加载配置文件

        Returns:
            配置字典
        """
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"配置文件不存在: {self.config_path}")

        with open(self.config_path, 'r', encoding='utf-8') as f:
            self._config = json.load(f)

        return self._config

    @property
    def config(self) -> Dict[str, Any]:
        """获取完整配置"""
        return self._config

    @property
    def okx_config(self) -> Dict[str, Any]:
        """获取OKX交易所配置"""
        return self._config.get('okx', {})

    @property
    def trading_pairs(self) -> Dict[str, Any]:
        """获取交易对配置"""
        return self._config.get('tradingPairs', {})

    @property
    def monitor_interval(self) -> int:
        """获取监控间隔（秒）"""
        return self._config.get('monitor_interval', 60)

    @property
    def feishu_webhook(self) -> str:
        """获取飞书webhook地址"""
        return self._config.get('feishu_webhook', '')

    @property
    def leverage(self) -> int:
        """获取杠杆倍数"""
        return self._config.get('leverage', 10)

    def get_pair_config(self, inst_id: str) -> Dict[str, Any]:
        """
        获取特定交易对的配置

        Args:
            inst_id: 交易对ID

        Returns:
            交易对配置字典
        """
        return self.trading_pairs.get(inst_id, {})
