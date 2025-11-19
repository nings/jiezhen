import time
import json
import logging
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from logging.handlers import TimedRotatingFileHandler
from typing import Dict, List, Optional, Tuple
from collections import deque
import okx.Trade_api as TradeAPI
import okx.Public_api as PublicAPI
import okx.Market_api as MarketAPI
import okx.Account_api as AccountAPI
import pandas as pd
import numpy as np

# 常量定义
DEFAULT_MONITOR_INTERVAL = 10  # 中频交易：10秒周期
DEFAULT_LEVERAGE = 10
DEFAULT_BATCH_SIZE = 5
DEFAULT_ATR_PERIOD = 60
DEFAULT_KLINE_LIMIT = 241
DEFAULT_EMA_PERIOD = 240
DEFAULT_AMOUNT_USDT = 20
DEFAULT_VALUE_MULTIPLIER = 2
MAX_RETRIES = 3
RETRY_DELAY = 2

# 订单簿分析参数
ORDERBOOK_DEPTH = 20  # 获取20档深度
OBI_THRESHOLD = 0.3  # 订单簿失衡阈值
SPREAD_MULTIPLIER = 2.0  # 价差倍数
SIGNAL_CONFIDENCE_THRESHOLD = 0.7  # 信号置信度阈值

# 读取配置文件
def load_config(config_path='config.json'):
    """加载并验证配置文件"""
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)

        if 'okx' not in config:
            raise ValueError("配置文件缺少 'okx' 字段")

        okx_config = config['okx']
        required_fields = ['apiKey', 'secret', 'password']
        for field in required_fields:
            if field not in okx_config or not okx_config[field]:
                raise ValueError(f"OKX配置缺少必需字段: {field}")

        return config
    except FileNotFoundError:
        raise FileNotFoundError(f"配置文件未找到: {config_path}")
    except json.JSONDecodeError as e:
        raise ValueError(f"配置文件JSON格式错误: {e}")

# 加载配置
config = load_config()

# 提取配置
okx_config = config['okx']
trading_pairs_config = config.get('tradingPairs', {})
monitor_interval = config.get('monitor_interval', DEFAULT_MONITOR_INTERVAL)
feishu_webhook = config.get('feishu_webhook', '')
leverage_value = config.get('leverage', DEFAULT_LEVERAGE)

# 初始化API
trade_api = TradeAPI.TradeAPI(okx_config["apiKey"], okx_config["secret"], okx_config["password"], False, '0')
market_api = MarketAPI.MarketAPI(okx_config["apiKey"], okx_config["secret"], okx_config["password"], False, '0')
public_api = PublicAPI.PublicAPI(okx_config["apiKey"], okx_config["secret"], okx_config["password"], False, '0')
account_api = AccountAPI.AccountAPI(okx_config["apiKey"], okx_config["secret"], okx_config["password"], False, '0')

# 日志配置
log_file = "log/okx_orderbook.log"
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

file_handler = TimedRotatingFileHandler(log_file, when='midnight', interval=1, backupCount=7, encoding='utf-8')
file_handler.suffix = "%Y-%m-%d"
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

instrument_info_dict = {}

# ============================================================================
# 基础功能函数
# ============================================================================

def fetch_and_store_all_instruments(instType='SWAP'):
    """获取并存储所有交易工具信息"""
    try:
        logger.info(f"正在获取交易工具信息，类型: {instType}")
        response = public_api.get_instruments(instType=instType)
        if 'data' in response and len(response['data']) > 0:
            instrument_info_dict.clear()
            for instrument in response['data']:
                instId = instrument['instId']
                instrument_info_dict[instId] = instrument
            logger.info(f"成功加载 {len(instrument_info_dict)} 个交易工具")
        else:
            raise ValueError("无法获取交易工具数据或数据为空")
    except Exception as e:
        logger.error(f"获取交易工具信息失败: {e}")
        raise

def send_feishu_notification(message):
    """发送飞书通知，带重试机制"""
    if not feishu_webhook:
        return

    headers = {'Content-Type': 'application/json'}
    data = {"msg_type": "text", "content": {"text": message}}

    for attempt in range(MAX_RETRIES):
        try:
            response = requests.post(feishu_webhook, headers=headers, json=data, timeout=10)
            if response.status_code == 200:
                logger.info("飞书通知发送成功")
                return
            else:
                logger.warning(f"飞书通知发送失败 (尝试 {attempt + 1}/{MAX_RETRIES}): {response.text}")
        except requests.exceptions.RequestException as e:
            logger.warning(f"飞书通知请求异常 (尝试 {attempt + 1}/{MAX_RETRIES}): {e}")

        if attempt < MAX_RETRIES - 1:
            time.sleep(RETRY_DELAY)

    logger.error("飞书通知发送失败，已达最大重试次数")

# ============================================================================
# 订单簿分析核心功能
# ============================================================================

class OrderBookAnalyzer:
    """订单簿分析器 - 实现HFT微观结构特征"""

    def __init__(self, instId: str):
        self.instId = instId
        self.history = deque(maxlen=100)  # 保留最近100次订单簿快照

    def get_orderbook(self, depth: int = ORDERBOOK_DEPTH) -> Optional[Dict]:
        """
        获取订单簿深度数据

        Returns:
            {
                'bids': [[price, size, ...], ...],
                'asks': [[price, size, ...], ...],
                'timestamp': int
            }
        """
        try:
            response = market_api.get_orderbook(instId=self.instId, sz=str(depth))
            if 'data' in response and len(response['data']) > 0:
                data = response['data'][0]
                orderbook = {
                    'bids': [[float(bid[0]), float(bid[1])] for bid in data.get('bids', [])],
                    'asks': [[float(ask[0]), float(ask[1])] for ask in data.get('asks', [])],
                    'timestamp': int(data.get('ts', 0))
                }
                self.history.append(orderbook)
                return orderbook
            return None
        except Exception as e:
            logger.error(f"{self.instId} 获取订单簿失败: {e}")
            return None

    def calculate_spread(self, orderbook: Dict) -> float:
        """
        特征#1: 最佳买卖价差 (Best Bid-Ask Spread)
        """
        if not orderbook or not orderbook['bids'] or not orderbook['asks']:
            return 0.0

        best_bid = orderbook['bids'][0][0]
        best_ask = orderbook['asks'][0][0]
        spread = best_ask - best_bid
        return spread

    def calculate_depth(self, orderbook: Dict, levels: int = 5) -> Tuple[float, float]:
        """
        特征#2: 买卖盘深度 (Order Book Depth)

        Returns:
            (bid_depth, ask_depth)
        """
        if not orderbook:
            return 0.0, 0.0

        bid_depth = sum(size for _, size in orderbook['bids'][:levels])
        ask_depth = sum(size for _, size in orderbook['asks'][:levels])

        return bid_depth, ask_depth

    def calculate_wap(self, orderbook: Dict) -> float:
        """
        特征#3: 加权平均价格 (Weighted Average Price)
        WAP = (BestBid * AskSize + BestAsk * BidSize) / (BidSize + AskSize)
        """
        if not orderbook or not orderbook['bids'] or not orderbook['asks']:
            return 0.0

        best_bid, bid_size = orderbook['bids'][0]
        best_ask, ask_size = orderbook['asks'][0]

        if bid_size + ask_size == 0:
            return (best_bid + best_ask) / 2

        wap = (best_bid * ask_size + best_ask * bid_size) / (bid_size + ask_size)
        return wap

    def calculate_quote_slope(self, orderbook: Dict, levels: int = 5) -> Tuple[float, float]:
        """
        特征#4: 报价斜率 (Quote Slope)
        计算订单簿价格与累积数量的关系斜率
        """
        if not orderbook:
            return 0.0, 0.0

        def calc_slope(orders, is_bid=True):
            if len(orders) < 2:
                return 0.0

            cumulative_qty = 0
            points = []
            for price, size in orders[:levels]:
                cumulative_qty += size
                points.append((cumulative_qty, price))

            if len(points) < 2:
                return 0.0

            # 简单线性回归计算斜率
            x = np.array([p[0] for p in points])
            y = np.array([p[1] for p in points])

            if len(x) > 1:
                slope = (y[-1] - y[0]) / (x[-1] - x[0]) if x[-1] != x[0] else 0.0
                return slope
            return 0.0

        bid_slope = calc_slope(orderbook['bids'], True)
        ask_slope = calc_slope(orderbook['asks'], False)

        return bid_slope, ask_slope

    def calculate_obi(self, orderbook: Dict, levels: int = 10) -> float:
        """
        特征#6: 订单簿失衡 (Order Book Imbalance)
        OBI = (Total Bid Volume - Total Ask Volume) / (Total Bid Volume + Total Ask Volume)

        返回值范围: [-1, 1]
        - 接近 1: 买盘压力大
        - 接近 -1: 卖盘压力大
        - 接近 0: 平衡
        """
        if not orderbook:
            return 0.0

        bid_volume = sum(size for _, size in orderbook['bids'][:levels])
        ask_volume = sum(size for _, size in orderbook['asks'][:levels])

        total_volume = bid_volume + ask_volume
        if total_volume == 0:
            return 0.0

        obi = (bid_volume - ask_volume) / total_volume
        return obi

    def calculate_micro_volatility(self, window: int = 20) -> float:
        """
        特征#13: 微观价格波动率 (Micro-price Volatility)
        基于WAP的短期波动率
        """
        if len(self.history) < window:
            return 0.0

        waps = [self.calculate_wap(ob) for ob in list(self.history)[-window:]]
        if not waps or all(w == 0 for w in waps):
            return 0.0

        returns = np.diff(waps) / waps[:-1]
        volatility = np.std(returns) if len(returns) > 0 else 0.0
        return volatility

    def detect_large_orders(self, orderbook: Dict, threshold_multiplier: float = 3.0) -> Dict:
        """
        特征#10: 大单追踪 (Large Lot Tracker)
        识别异常大的订单
        """
        if not orderbook:
            return {'bid_large': [], 'ask_large': []}

        # 计算平均订单大小
        all_sizes = [size for _, size in orderbook['bids'][:10]] + \
                    [size for _, size in orderbook['asks'][:10]]

        if not all_sizes:
            return {'bid_large': [], 'ask_large': []}

        avg_size = np.mean(all_sizes)
        threshold = avg_size * threshold_multiplier

        bid_large = [order for order in orderbook['bids'] if order[1] >= threshold]
        ask_large = [order for order in orderbook['asks'] if order[1] >= threshold]

        return {
            'bid_large': bid_large,
            'ask_large': ask_large,
            'threshold': threshold
        }

    def generate_signal(self, orderbook: Dict, market_price: float) -> Dict:
        """
        信号生成引擎
        综合多个微观结构特征，生成交易信号

        Returns:
            {
                'action': 'BUY' | 'SELL' | 'HOLD',
                'confidence': float (0-1),
                'features': {...},
                'reason': str
            }
        """
        if not orderbook:
            return {'action': 'HOLD', 'confidence': 0.0, 'reason': '订单簿数据无效'}

        # 计算所有特征
        features = {
            'spread': self.calculate_spread(orderbook),
            'bid_depth': self.calculate_depth(orderbook)[0],
            'ask_depth': self.calculate_depth(orderbook)[1],
            'wap': self.calculate_wap(orderbook),
            'bid_slope': self.calculate_quote_slope(orderbook)[0],
            'ask_slope': self.calculate_quote_slope(orderbook)[1],
            'obi': self.calculate_obi(orderbook),
            'micro_vol': self.calculate_micro_volatility(),
            'large_orders': self.detect_large_orders(orderbook)
        }

        # 信号生成逻辑
        action = 'HOLD'
        confidence = 0.0
        reasons = []

        obi = features['obi']
        spread = features['spread']
        wap = features['wap']

        # 1. 订单簿失衡信号（核心）
        if obi > OBI_THRESHOLD:
            action = 'BUY'
            confidence += 0.4
            reasons.append(f"买盘压力大(OBI={obi:.3f})")
        elif obi < -OBI_THRESHOLD:
            action = 'SELL'
            confidence += 0.4
            reasons.append(f"卖盘压力大(OBI={obi:.3f})")

        # 2. 深度不平衡确认
        bid_depth = features['bid_depth']
        ask_depth = features['ask_depth']
        depth_ratio = bid_depth / ask_depth if ask_depth > 0 else 1.0

        if depth_ratio > 1.5 and action == 'BUY':
            confidence += 0.2
            reasons.append(f"买盘深度优势(比例={depth_ratio:.2f})")
        elif depth_ratio < 0.67 and action == 'SELL':
            confidence += 0.2
            reasons.append(f"卖盘深度优势(比例={depth_ratio:.2f})")

        # 3. 大单支持
        large_orders = features['large_orders']
        if len(large_orders['bid_large']) > 0 and action == 'BUY':
            confidence += 0.15
            reasons.append(f"发现{len(large_orders['bid_large'])}个大买单")
        elif len(large_orders['ask_large']) > 0 and action == 'SELL':
            confidence += 0.15
            reasons.append(f"发现{len(large_orders['ask_large'])}个大卖单")

        # 4. 价差检查（流动性过滤）
        if wap > 0:
            spread_pct = (spread / wap) * 100
            if spread_pct > 0.5:  # 价差超过0.5%，流动性不足
                confidence *= 0.5
                reasons.append(f"价差过大({spread_pct:.3f}%)")

        # 5. 波动性调整
        if features['micro_vol'] > 0.01:  # 高波动
            confidence *= 0.8
            reasons.append("高波动环境")

        # 置信度归一化
        confidence = min(confidence, 1.0)

        return {
            'action': action if confidence >= SIGNAL_CONFIDENCE_THRESHOLD else 'HOLD',
            'confidence': confidence,
            'features': features,
            'reason': '; '.join(reasons) if reasons else '无明确信号'
        }

# ============================================================================
# 交易执行功能
# ============================================================================

def get_mark_price(instId):
    """获取交易对的当前市场价格"""
    try:
        response = market_api.get_ticker(instId)
        if 'data' in response and len(response['data']) > 0:
            last_price = response['data'][0]['last']
            return float(last_price)
        else:
            raise ValueError(f"{instId} 无法获取市场价格数据")
    except Exception as e:
        logger.error(f"{instId} 获取价格失败: {e}")
        raise

def round_price_to_tick(price, tick_size):
    """将价格调整为tick_size的整数倍"""
    tick_decimals = len(f"{tick_size:.10f}".rstrip('0').split('.')[1]) if '.' in f"{tick_size:.10f}" else 0
    adjusted_price = round(price / tick_size) * tick_size
    return f"{adjusted_price:.{tick_decimals}f}"

def cancel_all_orders(instId):
    """取消指定交易对的所有挂单"""
    try:
        open_orders = trade_api.get_order_list(instId=instId, state='live')

        if 'code' in open_orders and open_orders['code'] != '0':
            logger.warning(f"{instId} 获取挂单列表失败: {open_orders.get('msg', 'Unknown error')}")
            return

        if 'data' not in open_orders or not open_orders['data']:
            return

        order_ids = [order['ordId'] for order in open_orders['data']]
        if not order_ids:
            return

        # 批量取消
        batch_size = 20
        for i in range(0, len(order_ids), batch_size):
            batch_ids = order_ids[i:i + batch_size]
            cancel_params = [{'instId': instId, 'ordId': ord_id} for ord_id in batch_ids]

            try:
                result = trade_api.cancel_multiple_orders(cancel_params)
                if result.get('code') == '0':
                    logger.info(f"{instId} 成功取消 {len(batch_ids)} 个挂单")
            except Exception as e:
                logger.warning(f"{instId} 批量取消失败: {e}")
                for ord_id in batch_ids:
                    try:
                        trade_api.cancel_order(instId=instId, ordId=ord_id)
                    except Exception as cancel_error:
                        logger.error(f"{instId} 取消订单失败: {cancel_error}")

    except Exception as e:
        logger.error(f"{instId} 取消挂单时发生错误: {e}")

def set_leverage(instId, leverage, mgnMode='isolated', posSide=None):
    """设置杠杆"""
    try:
        body = {
            "instId": instId,
            "lever": str(leverage),
            "mgnMode": mgnMode
        }
        if mgnMode == 'isolated' and posSide:
            body["posSide"] = posSide
        response = account_api.set_leverage(**body)
        if response['code'] == '0':
            logger.info(f"{instId} 杠杆设置为 {leverage}x")
        else:
            logger.error(f"{instId} 设置杠杆失败: {response['msg']}")
    except Exception as e:
        logger.error(f"{instId} 设置杠杆错误: {e}")

def place_order(instId, price, amount_usdt, side):
    """下单"""
    if instId not in instrument_info_dict:
        logger.error(f"{instId} 交易工具信息未找到")
        return

    tick_size = float(instrument_info_dict[instId]['tickSz'])
    adjusted_price = round_price_to_tick(price, tick_size)

    response = public_api.convert_contract_coin(
        type='1', instId=instId, sz=str(amount_usdt),
        px=str(adjusted_price), unit='usdt', opType='open'
    )

    if response['code'] == '0':
        sz = response['data'][0]['sz']
        if float(sz) > 0:
            pos_side = 'long' if side == 'buy' else 'short'
            set_leverage(instId, leverage_value, mgnMode='isolated', posSide=pos_side)
            order_result = trade_api.place_order(
                instId=instId,
                tdMode='isolated',
                posSide=pos_side,
                side=side,
                ordType='limit',
                sz=sz,
                px=str(adjusted_price)
            )
            logger.info(f"{instId} 下单成功: {order_result}")
        else:
            logger.info(f"{instId} 合约张数太小，无法下单")
    else:
        logger.warning(f"{instId} 转换失败: {response['msg']}")

# ============================================================================
# 策略执行主逻辑
# ============================================================================

def process_pair_orderbook(instId: str, pair_config: Dict):
    """
    基于订单簿分析的交易策略

    Args:
        instId: 交易对ID
        pair_config: 配置参数
    """
    try:
        # 创建订单簿分析器
        analyzer = OrderBookAnalyzer(instId)

        # 获取当前市场价格
        mark_price = get_mark_price(instId)

        # 获取订单簿数据
        orderbook = analyzer.get_orderbook(depth=ORDERBOOK_DEPTH)
        if not orderbook:
            logger.warning(f"{instId} 订单簿数据获取失败")
            return

        # 生成交易信号
        signal = analyzer.generate_signal(orderbook, mark_price)

        logger.info(f"{instId} 信号: {signal['action']}, 置信度: {signal['confidence']:.2%}, 原因: {signal['reason']}")

        # 特征日志
        features = signal['features']
        logger.info(
            f"{instId} 特征 - "
            f"OBI: {features['obi']:.3f}, "
            f"价差: {features['spread']:.6f}, "
            f"WAP: {features['wap']:.6f}, "
            f"买深度: {features['bid_depth']:.2f}, "
            f"卖深度: {features['ask_depth']:.2f}"
        )

        # 取消旧挂单
        cancel_all_orders(instId)

        # 执行交易
        action = signal['action']
        confidence = signal['confidence']

        if action == 'HOLD':
            logger.info(f"{instId} 信号不足，不操作")
            return

        # 获取配置
        amount_usdt = pair_config.get('long_amount_usdt' if action == 'BUY' else 'short_amount_usdt', DEFAULT_AMOUNT_USDT)

        # 根据置信度调整交易金额
        adjusted_amount = amount_usdt * confidence

        # 计算挂单价格（使用WAP和价差）
        wap = features['wap']
        spread = features['spread']

        if action == 'BUY':
            # 在最佳买价附近挂单
            target_price = wap - spread * 0.3  # 略低于WAP，争取被动成交
            place_order(instId, target_price, adjusted_amount, 'buy')
            logger.info(f"{instId} 挂买单: 价格={target_price:.6f}, 金额={adjusted_amount:.2f} USDT")

        elif action == 'SELL':
            # 在最佳卖价附近挂单
            target_price = wap + spread * 0.3  # 略高于WAP
            place_order(instId, target_price, adjusted_amount, 'sell')
            logger.info(f"{instId} 挂卖单: 价格={target_price:.6f}, 金额={adjusted_amount:.2f} USDT")

    except Exception as e:
        error_message = f'{instId} 处理失败: {e}'
        logger.error(error_message, exc_info=True)
        send_feishu_notification(error_message)

def main():
    """主函数"""
    logger.info("=" * 60)
    logger.info("订单簿分析交易机器人启动")
    logger.info(f"监控间隔: {monitor_interval}秒 (中频模式)")
    logger.info(f"杠杆倍数: {leverage_value}x")
    logger.info(f"订单簿深度: {ORDERBOOK_DEPTH}档")
    logger.info(f"OBI阈值: {OBI_THRESHOLD}")
    logger.info("=" * 60)

    try:
        fetch_and_store_all_instruments()

        inst_ids = list(trading_pairs_config.keys())
        if not inst_ids:
            logger.error("配置文件中没有交易对，程序退出")
            return

        logger.info(f"已配置 {len(inst_ids)} 个交易对: {', '.join(inst_ids)}")

        batch_size = DEFAULT_BATCH_SIZE
        loop_count = 0

        while True:
            loop_count += 1
            logger.info(f"\n{'='*60}")
            logger.info(f"第 {loop_count} 轮处理开始")
            logger.info(f"{'='*60}")

            try:
                for i in range(0, len(inst_ids), batch_size):
                    batch = inst_ids[i:i + batch_size]
                    logger.info(f"处理批次 {i//batch_size + 1}: {', '.join(batch)}")

                    with ThreadPoolExecutor(max_workers=batch_size) as executor:
                        futures = {
                            executor.submit(process_pair_orderbook, instId, trading_pairs_config[instId]): instId
                            for instId in batch
                        }

                        for future in as_completed(futures):
                            inst_id = futures[future]
                            try:
                                future.result()
                            except Exception as e:
                                logger.error(f"{inst_id} 处理异常: {e}", exc_info=True)

            except KeyboardInterrupt:
                logger.info("收到终止信号，正在退出...")
                break
            except Exception as e:
                logger.error(f"主循环发生异常: {e}", exc_info=True)
                send_feishu_notification(f"交易机器人主循环异常: {e}")

            logger.info(f"第 {loop_count} 轮处理完成，等待 {monitor_interval} 秒后继续...\n")
            time.sleep(monitor_interval)

    except KeyboardInterrupt:
        logger.info("程序被用户中断")
    except Exception as e:
        logger.error(f"程序启动失败: {e}", exc_info=True)
        send_feishu_notification(f"交易机器人启动失败: {e}")
    finally:
        logger.info("订单簿分析交易机器人已停止")

if __name__ == '__main__':
    main()
