"""
交易品种管理模块
负责管理交易品种信息
"""
from typing import Dict, Any
from src.core.api_client import OKXClient
from src.utils.logger import Logger

logger = Logger.get_logger(__name__)


class InstrumentManager:
    """交易品种管理器"""

    def __init__(self, client: OKXClient):
        """
        初始化交易品种管理器

        Args:
            client: OKX客户端
        """
        self.client = client
        self.instruments: Dict[str, Dict[str, Any]] = {}

    def fetch_all_instruments(self, inst_type: str = 'SWAP') -> None:
        """
        获取并存储所有交易品种信息

        Args:
            inst_type: 产品类型
        """
        try:
            logger.info(f"Fetching all instruments for type: {inst_type}")
            response = self.client.get_instruments(inst_type=inst_type)

            if 'data' in response and len(response['data']) > 0:
                self.instruments.clear()
                for instrument in response['data']:
                    inst_id = instrument['instId']
                    self.instruments[inst_id] = instrument
                    logger.info(f"Stored instrument: {inst_id}")
            else:
                raise ValueError("Unexpected response structure or no instrument data available")

        except Exception as e:
            logger.error(f"Error fetching instruments: {e}")
            raise

    def get_instrument(self, inst_id: str) -> Dict[str, Any]:
        """
        获取指定交易品种信息

        Args:
            inst_id: 交易对ID

        Returns:
            交易品种信息
        """
        if inst_id not in self.instruments:
            raise ValueError(f"Instrument {inst_id} not found in cache")
        return self.instruments[inst_id]

    def get_tick_size(self, inst_id: str) -> float:
        """
        获取最小价格变动单位

        Args:
            inst_id: 交易对ID

        Returns:
            最小价格变动单位
        """
        instrument = self.get_instrument(inst_id)
        return float(instrument['tickSz'])

    def has_instrument(self, inst_id: str) -> bool:
        """
        检查交易品种是否存在

        Args:
            inst_id: 交易对ID

        Returns:
            是否存在
        """
        return inst_id in self.instruments
