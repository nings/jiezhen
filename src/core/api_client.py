"""
OKX API客户端封装
提供统一的API调用接口
"""
from typing import Dict, Any, List
import okx.Trade_api as TradeAPI
import okx.Public_api as PublicAPI
import okx.Market_api as MarketAPI
import okx.Account_api as AccountAPI
from src.utils.logger import Logger

logger = Logger.get_logger(__name__)


class OKXClient:
    """OKX交易所API客户端"""

    def __init__(self, api_key: str, secret: str, password: str, flag: str = '0'):
        """
        初始化OKX客户端

        Args:
            api_key: API密钥
            secret: API密钥
            password: API密码
            flag: 模拟盘标志，'0'为实盘，'1'为模拟盘
        """
        self.api_key = api_key
        self.secret = secret
        self.password = password
        self.flag = flag

        # 初始化各个API
        self.trade_api = TradeAPI.TradeAPI(api_key, secret, password, False, flag)
        self.market_api = MarketAPI.MarketAPI(api_key, secret, password, False, flag)
        self.public_api = PublicAPI.PublicAPI(api_key, secret, password, False, flag)
        self.account_api = AccountAPI.AccountAPI(api_key, secret, password, False, flag)

    def get_ticker(self, inst_id: str) -> Dict[str, Any]:
        """
        获取ticker信息

        Args:
            inst_id: 交易对ID

        Returns:
            ticker数据
        """
        return self.market_api.get_ticker(inst_id)

    def get_mark_price(self, inst_id: str) -> float:
        """
        获取标记价格

        Args:
            inst_id: 交易对ID

        Returns:
            标记价格
        """
        response = self.get_ticker(inst_id)
        if 'data' in response and len(response['data']) > 0:
            last_price = response['data'][0]['last']
            return float(last_price)
        else:
            raise ValueError("Unexpected response structure or missing 'last' key")

    def get_candlesticks(self, inst_id: str, bar: str = '1m', limit: int = 241) -> List[List]:
        """
        获取K线数据

        Args:
            inst_id: 交易对ID
            bar: K线周期
            limit: 获取数量

        Returns:
            K线数据列表
        """
        response = self.market_api.get_candlesticks(inst_id, bar=bar, limit=limit)
        if 'data' in response and len(response['data']) > 0:
            return response['data']
        else:
            raise ValueError("Unexpected response structure or missing candlestick data")

    def get_instruments(self, inst_type: str = 'SWAP') -> Dict[str, Any]:
        """
        获取交易产品信息

        Args:
            inst_type: 产品类型

        Returns:
            产品信息字典
        """
        return self.public_api.get_instruments(instType=inst_type)

    def convert_contract_coin(self, inst_id: str, sz: str, px: str,
                              type: str = '1', unit: str = 'usdt',
                              op_type: str = 'open') -> Dict[str, Any]:
        """
        币币/合约换算

        Args:
            inst_id: 交易对ID
            sz: 数量
            px: 价格
            type: 换算类型
            unit: 单位
            op_type: 操作类型

        Returns:
            换算结果
        """
        return self.public_api.convert_contract_coin(
            type=type,
            instId=inst_id,
            sz=sz,
            px=px,
            unit=unit,
            opType=op_type
        )

    def set_leverage(self, inst_id: str, lever: int, mgn_mode: str = 'isolated',
                     pos_side: str = None) -> Dict[str, Any]:
        """
        设置杠杆

        Args:
            inst_id: 交易对ID
            lever: 杠杆倍数
            mgn_mode: 保证金模式
            pos_side: 持仓方向

        Returns:
            设置结果
        """
        body = {
            "instId": inst_id,
            "lever": str(lever),
            "mgnMode": mgn_mode
        }
        if mgn_mode == 'isolated' and pos_side:
            body["posSide"] = pos_side

        return self.account_api.set_leverage(**body)

    def place_order(self, inst_id: str, td_mode: str, pos_side: str,
                    side: str, ord_type: str, sz: str, px: str) -> Dict[str, Any]:
        """
        下单

        Args:
            inst_id: 交易对ID
            td_mode: 交易模式
            pos_side: 持仓方向
            side: 订单方向
            ord_type: 订单类型
            sz: 数量
            px: 价格

        Returns:
            下单结果
        """
        return self.trade_api.place_order(
            instId=inst_id,
            tdMode=td_mode,
            posSide=pos_side,
            side=side,
            ordType=ord_type,
            sz=sz,
            px=px
        )

    def cancel_order(self, inst_id: str, ord_id: str) -> Dict[str, Any]:
        """
        取消订单

        Args:
            inst_id: 交易对ID
            ord_id: 订单ID

        Returns:
            取消结果
        """
        return self.trade_api.cancel_order(instId=inst_id, ordId=ord_id)

    def get_order_list(self, inst_id: str, state: str = 'live') -> Dict[str, Any]:
        """
        获取订单列表

        Args:
            inst_id: 交易对ID
            state: 订单状态

        Returns:
            订单列表
        """
        return self.trade_api.get_order_list(instId=inst_id, state=state)
