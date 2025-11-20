#!/usr/bin/env python3
"""
WebSocket实时数据流

功能：
- 实时订单簿数据
- 实时交易数据
- 实时Ticker数据
- 自动重连机制
- 数据缓存
"""

import websocket
import json
import threading
import time
import logging
from collections import deque
from typing import Dict, List, Callable, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class OKXWebSocket:
    """OKX WebSocket客户端"""

    def __init__(self, is_public=True):
        """
        初始化WebSocket客户端

        Args:
            is_public: 是否为公共频道（不需要登录）
        """
        self.is_public = is_public
        self.url = "wss://ws.okx.com:8443/ws/v5/public" if is_public else "wss://ws.okx.com:8443/ws/v5/private"
        self.ws = None
        self.thread = None
        self.is_running = False

        # 数据缓存
        self.orderbook_cache = {}
        self.ticker_cache = {}
        self.trades_cache = {}

        # 回调函数
        self.callbacks = {
            'orderbook': [],
            'ticker': [],
            'trades': [],
            'error': []
        }

        # 订阅列表
        self.subscriptions = []

        # 心跳
        self.last_ping_time = 0
        self.ping_interval = 20  # 20秒发送一次ping

    def on_message(self, ws, message):
        """处理消息"""
        try:
            data = json.loads(message)

            # 处理订阅确认
            if 'event' in data:
                if data['event'] == 'subscribe':
                    logger.info(f"订阅成功: {data.get('arg', {}).get('channel')}")
                elif data['event'] == 'error':
                    logger.error(f"错误: {data.get('msg')}")
                    self._trigger_callbacks('error', data)
                return

            # 处理数据推送
            if 'data' in data and 'arg' in data:
                channel = data['arg']['channel']
                inst_id = data['arg'].get('instId', '')

                if channel == 'books' or channel == 'books5':
                    self._handle_orderbook(inst_id, data['data'])
                elif channel == 'tickers':
                    self._handle_ticker(inst_id, data['data'])
                elif channel == 'trades':
                    self._handle_trades(inst_id, data['data'])

        except Exception as e:
            logger.error(f"处理消息失败: {e}")
            self._trigger_callbacks('error', {'error': str(e)})

    def _handle_orderbook(self, inst_id: str, data: List[Dict]):
        """处理订单簿数据"""
        if not data:
            return

        orderbook_data = data[0]

        # 解析订单簿
        orderbook = {
            'bids': [[float(bid[0]), float(bid[1])] for bid in orderbook_data.get('bids', [])],
            'asks': [[float(ask[0]), float(ask[1])] for ask in orderbook_data.get('asks', [])],
            'timestamp': int(orderbook_data.get('ts', 0)),
            'instId': inst_id
        }

        # 缓存
        self.orderbook_cache[inst_id] = orderbook

        # 触发回调
        self._trigger_callbacks('orderbook', orderbook)

    def _handle_ticker(self, inst_id: str, data: List[Dict]):
        """处理Ticker数据"""
        if not data:
            return

        ticker_data = data[0]

        ticker = {
            'instId': inst_id,
            'last': float(ticker_data.get('last', 0)),
            'bid': float(ticker_data.get('bidPx', 0)),
            'ask': float(ticker_data.get('askPx', 0)),
            'volume_24h': float(ticker_data.get('vol24h', 0)),
            'open_24h': float(ticker_data.get('open24h', 0)),
            'high_24h': float(ticker_data.get('high24h', 0)),
            'low_24h': float(ticker_data.get('low24h', 0)),
            'timestamp': int(ticker_data.get('ts', 0))
        }

        # 缓存
        self.ticker_cache[inst_id] = ticker

        # 触发回调
        self._trigger_callbacks('ticker', ticker)

    def _handle_trades(self, inst_id: str, data: List[Dict]):
        """处理成交数据"""
        if not data:
            return

        # 缓存最近100笔交易
        if inst_id not in self.trades_cache:
            self.trades_cache[inst_id] = deque(maxlen=100)

        for trade in data:
            trade_info = {
                'instId': inst_id,
                'price': float(trade.get('px', 0)),
                'size': float(trade.get('sz', 0)),
                'side': trade.get('side', ''),
                'timestamp': int(trade.get('ts', 0))
            }
            self.trades_cache[inst_id].append(trade_info)

        # 触发回调
        self._trigger_callbacks('trades', {'instId': inst_id, 'trades': data})

    def _trigger_callbacks(self, event_type: str, data: Dict):
        """触发回调函数"""
        for callback in self.callbacks.get(event_type, []):
            try:
                callback(data)
            except Exception as e:
                logger.error(f"回调函数执行失败: {e}")

    def on_error(self, ws, error):
        """错误处理"""
        logger.error(f"WebSocket错误: {error}")
        self._trigger_callbacks('error', {'error': str(error)})

    def on_close(self, ws, close_status_code, close_msg):
        """连接关闭"""
        logger.warning(f"WebSocket连接关闭: {close_status_code} - {close_msg}")
        self.is_running = False

        # 自动重连
        if close_status_code != 1000:  # 非正常关闭
            logger.info("5秒后尝试重连...")
            time.sleep(5)
            self.connect()

    def on_open(self, ws):
        """连接建立"""
        logger.info("WebSocket连接已建立")

        # 重新订阅
        if self.subscriptions:
            self._resubscribe()

        # 启动心跳
        self._start_ping()

    def _start_ping(self):
        """启动心跳"""
        def ping_loop():
            while self.is_running:
                try:
                    if time.time() - self.last_ping_time > self.ping_interval:
                        self.ws.send('ping')
                        self.last_ping_time = time.time()
                    time.sleep(5)
                except Exception as e:
                    logger.error(f"心跳发送失败: {e}")

        ping_thread = threading.Thread(target=ping_loop, daemon=True)
        ping_thread.start()

    def _resubscribe(self):
        """重新订阅"""
        if not self.subscriptions:
            return

        logger.info(f"重新订阅 {len(self.subscriptions)} 个频道")
        for sub in self.subscriptions:
            self.ws.send(json.dumps(sub))

    def connect(self):
        """连接WebSocket"""
        if self.is_running:
            logger.warning("WebSocket已经在运行")
            return

        self.is_running = True
        self.ws = websocket.WebSocketApp(
            self.url,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
            on_open=self.on_open
        )

        # 在新线程中运行
        self.thread = threading.Thread(target=self.ws.run_forever, daemon=True)
        self.thread.start()

        logger.info("WebSocket连接已启动")

    def disconnect(self):
        """断开连接"""
        self.is_running = False
        if self.ws:
            self.ws.close()
        logger.info("WebSocket连接已断开")

    def subscribe_orderbook(self, inst_id: str, depth: int = 5):
        """
        订阅订单簿

        Args:
            inst_id: 交易对ID
            depth: 深度（5档或400档）
        """
        channel = 'books5' if depth == 5 else 'books'

        sub_msg = {
            "op": "subscribe",
            "args": [{
                "channel": channel,
                "instId": inst_id
            }]
        }

        self.subscriptions.append(sub_msg)

        if self.ws and self.is_running:
            self.ws.send(json.dumps(sub_msg))
            logger.info(f"订阅订单簿: {inst_id} ({channel})")

    def subscribe_ticker(self, inst_id: str):
        """订阅Ticker"""
        sub_msg = {
            "op": "subscribe",
            "args": [{
                "channel": "tickers",
                "instId": inst_id
            }]
        }

        self.subscriptions.append(sub_msg)

        if self.ws and self.is_running:
            self.ws.send(json.dumps(sub_msg))
            logger.info(f"订阅Ticker: {inst_id}")

    def subscribe_trades(self, inst_id: str):
        """订阅成交数据"""
        sub_msg = {
            "op": "subscribe",
            "args": [{
                "channel": "trades",
                "instId": inst_id
            }]
        }

        self.subscriptions.append(sub_msg)

        if self.ws and self.is_running:
            self.ws.send(json.dumps(sub_msg))
            logger.info(f"订阅成交数据: {inst_id}")

    def register_callback(self, event_type: str, callback: Callable):
        """
        注册回调函数

        Args:
            event_type: 'orderbook', 'ticker', 'trades', 'error'
            callback: 回调函数
        """
        if event_type in self.callbacks:
            self.callbacks[event_type].append(callback)

    def get_orderbook(self, inst_id: str) -> Optional[Dict]:
        """获取缓存的订单簿"""
        return self.orderbook_cache.get(inst_id)

    def get_ticker(self, inst_id: str) -> Optional[Dict]:
        """获取缓存的Ticker"""
        return self.ticker_cache.get(inst_id)

    def get_recent_trades(self, inst_id: str, limit: int = 10) -> List[Dict]:
        """获取最近的成交记录"""
        trades = self.trades_cache.get(inst_id, [])
        return list(trades)[-limit:]


# 使用示例
if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # 创建WebSocket客户端
    ws_client = OKXWebSocket()

    # 注册回调
    def on_orderbook_update(data):
        print(f"订单簿更新: {data['instId']}, "
              f"最佳买价: {data['bids'][0][0] if data['bids'] else 'N/A'}, "
              f"最佳卖价: {data['asks'][0][0] if data['asks'] else 'N/A'}")

    def on_ticker_update(data):
        print(f"Ticker更新: {data['instId']}, 最新价: {data['last']}")

    ws_client.register_callback('orderbook', on_orderbook_update)
    ws_client.register_callback('ticker', on_ticker_update)

    # 连接
    ws_client.connect()

    # 订阅
    ws_client.subscribe_orderbook('BTC-USDT-SWAP')
    ws_client.subscribe_ticker('BTC-USDT-SWAP')

    # 保持运行
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        ws_client.disconnect()
        print("程序已退出")
