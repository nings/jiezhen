import time
import json
import logging
import requests
import pickle
import os
from datetime import datetime, timedelta
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
import lightgbm as lgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score

# 常量定义
DEFAULT_MONITOR_INTERVAL = 10
DEFAULT_LEVERAGE = 10
DEFAULT_BATCH_SIZE = 5
DEFAULT_AMOUNT_USDT = 20
MAX_RETRIES = 3
RETRY_DELAY = 2

# 机器学习参数
ORDERBOOK_DEPTH = 20
FEATURE_HISTORY_SIZE = 100
MIN_TRAINING_SAMPLES = 1000
MODEL_RETRAIN_INTERVAL = 3600 * 24  # 每24小时重训练一次
PREDICTION_THRESHOLD = 0.6  # 预测概率阈值
DATA_COLLECTION_MODE = False  # 是否处于数据收集模式

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
log_file = "log/okx_ml.log"
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
        except requests.exceptions.RequestException as e:
            logger.warning(f"飞书通知请求异常 (尝试 {attempt + 1}/{MAX_RETRIES}): {e}")

        if attempt < MAX_RETRIES - 1:
            time.sleep(RETRY_DELAY)

# ============================================================================
# 特征工程模块
# ============================================================================

class FeatureEngineer:
    """特征工程类 - 从市场数据中提取机器学习特征"""

    @staticmethod
    def get_orderbook(instId: str, depth: int = ORDERBOOK_DEPTH) -> Optional[Dict]:
        """获取订单簿数据"""
        try:
            response = market_api.get_orderbook(instId=instId, sz=str(depth))
            if 'data' in response and len(response['data']) > 0:
                data = response['data'][0]
                return {
                    'bids': [[float(bid[0]), float(bid[1])] for bid in data.get('bids', [])],
                    'asks': [[float(ask[0]), float(ask[1])] for ask in data.get('asks', [])],
                    'timestamp': int(data.get('ts', 0))
                }
            return None
        except Exception as e:
            logger.error(f"{instId} 获取订单簿失败: {e}")
            return None

    @staticmethod
    def get_ticker(instId: str) -> Optional[Dict]:
        """获取ticker数据"""
        try:
            response = market_api.get_ticker(instId)
            if 'data' in response and len(response['data']) > 0:
                data = response['data'][0]
                return {
                    'last': float(data.get('last', 0)),
                    'bid': float(data.get('bidPx', 0)),
                    'ask': float(data.get('askPx', 0)),
                    'volume_24h': float(data.get('vol24h', 0)),
                    'open_24h': float(data.get('open24h', 0)),
                    'high_24h': float(data.get('high24h', 0)),
                    'low_24h': float(data.get('low24h', 0))
                }
            return None
        except Exception as e:
            logger.error(f"{instId} 获取ticker失败: {e}")
            return None

    @staticmethod
    def get_klines(instId: str, bar='1m', limit=100) -> Optional[pd.DataFrame]:
        """获取K线数据并转换为DataFrame"""
        try:
            response = market_api.get_candlesticks(instId, bar=bar, limit=limit)
            if 'data' in response and len(response['data']) > 0:
                df = pd.DataFrame(response['data'], columns=[
                    'timestamp', 'open', 'high', 'low', 'close', 'volume', 'volCcy'
                ])
                df = df.astype({
                    'timestamp': 'int64',
                    'open': 'float64',
                    'high': 'float64',
                    'low': 'float64',
                    'close': 'float64',
                    'volume': 'float64'
                })
                df = df.sort_values('timestamp').reset_index(drop=True)
                return df
            return None
        except Exception as e:
            logger.error(f"{instId} 获取K线失败: {e}")
            return None

    @staticmethod
    def extract_orderbook_features(orderbook: Dict) -> Dict:
        """从订单簿提取特征"""
        if not orderbook or not orderbook['bids'] or not orderbook['asks']:
            return {}

        features = {}

        # 基础特征
        best_bid = orderbook['bids'][0][0]
        best_ask = orderbook['asks'][0][0]
        bid_size = orderbook['bids'][0][1]
        ask_size = orderbook['asks'][0][1]

        features['spread'] = best_ask - best_bid
        features['spread_pct'] = (features['spread'] / best_bid) * 100 if best_bid > 0 else 0
        features['mid_price'] = (best_bid + best_ask) / 2

        # WAP (加权平均价格)
        if bid_size + ask_size > 0:
            features['wap'] = (best_bid * ask_size + best_ask * bid_size) / (bid_size + ask_size)
        else:
            features['wap'] = features['mid_price']

        # 订单簿失衡 (OBI)
        levels = [5, 10, 20]
        for level in levels:
            bid_volume = sum(size for _, size in orderbook['bids'][:level])
            ask_volume = sum(size for _, size in orderbook['asks'][:level])
            total_volume = bid_volume + ask_volume

            if total_volume > 0:
                features[f'obi_{level}'] = (bid_volume - ask_volume) / total_volume
                features[f'bid_depth_{level}'] = bid_volume
                features[f'ask_depth_{level}'] = ask_volume
                features[f'depth_ratio_{level}'] = bid_volume / ask_volume if ask_volume > 0 else 1.0
            else:
                features[f'obi_{level}'] = 0
                features[f'bid_depth_{level}'] = 0
                features[f'ask_depth_{level}'] = 0
                features[f'depth_ratio_{level}'] = 1.0

        # 报价斜率
        if len(orderbook['bids']) >= 5 and len(orderbook['asks']) >= 5:
            bid_prices = [p for p, _ in orderbook['bids'][:5]]
            ask_prices = [p for p, _ in orderbook['asks'][:5]]

            features['bid_slope'] = (bid_prices[0] - bid_prices[-1]) / 5 if len(bid_prices) == 5 else 0
            features['ask_slope'] = (ask_prices[-1] - ask_prices[0]) / 5 if len(ask_prices) == 5 else 0

        # 大单检测
        all_sizes = [size for _, size in orderbook['bids'][:10]] + \
                    [size for _, size in orderbook['asks'][:10]]
        if all_sizes:
            avg_size = np.mean(all_sizes)
            std_size = np.std(all_sizes)

            large_threshold = avg_size + 2 * std_size
            features['large_bid_count'] = sum(1 for _, size in orderbook['bids'][:10] if size > large_threshold)
            features['large_ask_count'] = sum(1 for _, size in orderbook['asks'][:10] if size > large_threshold)

        return features

    @staticmethod
    def extract_ticker_features(ticker: Dict) -> Dict:
        """从ticker提取特征"""
        if not ticker:
            return {}

        features = {}

        features['last_price'] = ticker['last']
        features['volume_24h'] = ticker['volume_24h']

        # 24h价格变化
        if ticker['open_24h'] > 0:
            features['price_change_24h'] = ((ticker['last'] - ticker['open_24h']) / ticker['open_24h']) * 100
        else:
            features['price_change_24h'] = 0

        # 24h振幅
        if ticker['low_24h'] > 0:
            features['amplitude_24h'] = ((ticker['high_24h'] - ticker['low_24h']) / ticker['low_24h']) * 100
        else:
            features['amplitude_24h'] = 0

        return features

    @staticmethod
    def extract_technical_features(klines: pd.DataFrame) -> Dict:
        """从K线提取技术指标特征"""
        if klines is None or len(klines) < 20:
            return {}

        features = {}

        # EMA
        for period in [7, 14, 30, 60]:
            if len(klines) >= period:
                ema = klines['close'].ewm(span=period, adjust=False).mean().iloc[-1]
                features[f'ema_{period}'] = ema
                features[f'price_to_ema_{period}'] = (klines['close'].iloc[-1] / ema - 1) * 100 if ema > 0 else 0

        # ATR
        if len(klines) >= 14:
            high = klines['high']
            low = klines['low']
            close = klines['close']

            tr1 = high - low
            tr2 = abs(high - close.shift())
            tr3 = abs(low - close.shift())

            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            atr = tr.rolling(window=14).mean().iloc[-1]

            features['atr_14'] = atr
            if atr > 0:
                features['price_to_atr'] = klines['close'].iloc[-1] / atr

        # RSI
        if len(klines) >= 14:
            delta = klines['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()

            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            features['rsi_14'] = rsi.iloc[-1]

        # 成交量特征
        if len(klines) >= 20:
            features['volume_ma_20'] = klines['volume'].rolling(window=20).mean().iloc[-1]
            features['volume_ratio'] = klines['volume'].iloc[-1] / features['volume_ma_20'] if features['volume_ma_20'] > 0 else 1

        # 价格动量
        if len(klines) >= 10:
            features['momentum_5'] = ((klines['close'].iloc[-1] / klines['close'].iloc[-6]) - 1) * 100 if klines['close'].iloc[-6] > 0 else 0
            features['momentum_10'] = ((klines['close'].iloc[-1] / klines['close'].iloc[-11]) - 1) * 100 if klines['close'].iloc[-11] > 0 else 0

        # 波动率
        if len(klines) >= 20:
            returns = klines['close'].pct_change()
            features['volatility_20'] = returns.rolling(window=20).std().iloc[-1] * 100

        return features

    @classmethod
    def extract_all_features(cls, instId: str) -> Optional[Dict]:
        """提取所有特征"""
        try:
            features = {'timestamp': int(time.time() * 1000)}

            # 订单簿特征
            orderbook = cls.get_orderbook(instId)
            if orderbook:
                features.update(cls.extract_orderbook_features(orderbook))

            # Ticker特征
            ticker = cls.get_ticker(instId)
            if ticker:
                features.update(cls.extract_ticker_features(ticker))

            # 技术指标特征
            klines = cls.get_klines(instId, bar='1m', limit=100)
            if klines is not None:
                features.update(cls.extract_technical_features(klines))

            return features if len(features) > 10 else None

        except Exception as e:
            logger.error(f"{instId} 特征提取失败: {e}")
            return None

# ============================================================================
# 数据收集模块
# ============================================================================

class DataCollector:
    """数据收集器 - 收集训练数据"""

    def __init__(self, instId: str, data_dir='ml_data'):
        self.instId = instId
        self.data_dir = data_dir
        self.data_file = f"{data_dir}/{instId.replace('-', '_')}_data.csv"

        os.makedirs(data_dir, exist_ok=True)

        # 如果文件存在，加载历史数据
        if os.path.exists(self.data_file):
            self.data = pd.read_csv(self.data_file)
            logger.info(f"{instId} 加载历史数据: {len(self.data)} 条")
        else:
            self.data = pd.DataFrame()
            logger.info(f"{instId} 创建新数据文件")

    def collect_sample(self, features: Dict, label: Optional[int] = None):
        """
        收集单个样本

        Args:
            features: 特征字典
            label: 标签 (1=上涨, 0=下跌, None=未知)
        """
        sample = features.copy()
        if label is not None:
            sample['label'] = label

        self.data = pd.concat([self.data, pd.DataFrame([sample])], ignore_index=True)

    def update_labels(self, lookforward_minutes=5, price_threshold=0.3):
        """
        更新标签：根据未来价格变化标注样本

        Args:
            lookforward_minutes: 向前看N分钟
            price_threshold: 价格变化阈值(%)
        """
        if len(self.data) < lookforward_minutes + 1:
            return

        # 只更新没有标签的数据
        unlabeled = self.data[self.data['label'].isna()]

        for idx in unlabeled.index:
            if idx + lookforward_minutes >= len(self.data):
                continue

            current_price = self.data.loc[idx, 'mid_price']
            future_price = self.data.loc[idx + lookforward_minutes, 'mid_price']

            if current_price > 0:
                price_change_pct = ((future_price - current_price) / current_price) * 100

                if price_change_pct > price_threshold:
                    self.data.loc[idx, 'label'] = 1  # 上涨
                elif price_change_pct < -price_threshold:
                    self.data.loc[idx, 'label'] = 0  # 下跌
                else:
                    self.data.loc[idx, 'label'] = 2  # 横盘（可选择不使用）

    def save(self):
        """保存数据到文件"""
        self.data.to_csv(self.data_file, index=False)
        logger.info(f"{self.instId} 数据已保存: {len(self.data)} 条")

    def get_training_data(self, min_samples=MIN_TRAINING_SAMPLES):
        """
        获取训练数据

        Returns:
            (X, y) 或 None
        """
        # 过滤有标签的数据
        labeled_data = self.data[self.data['label'].notna()]

        if len(labeled_data) < min_samples:
            logger.warning(f"{self.instId} 数据不足: {len(labeled_data)} < {min_samples}")
            return None, None

        # 移除非特征列
        feature_cols = [col for col in labeled_data.columns if col not in ['label', 'timestamp']]

        X = labeled_data[feature_cols].fillna(0)
        y = labeled_data['label']

        return X, y

# ============================================================================
# 机器学习模型
# ============================================================================

class MLModel:
    """机器学习模型封装"""

    def __init__(self, instId: str, model_dir='ml_models'):
        self.instId = instId
        self.model_dir = model_dir
        self.model_file = f"{model_dir}/{instId.replace('-', '_')}_model.pkl"
        self.model = None
        self.feature_names = None
        self.last_train_time = None

        os.makedirs(model_dir, exist_ok=True)

        # 尝试加载已有模型
        self.load()

    def train(self, X: pd.DataFrame, y: pd.Series):
        """
        训练模型

        Args:
            X: 特征
            y: 标签
        """
        logger.info(f"{self.instId} 开始训练模型，样本数: {len(X)}")

        # 保存特征名
        self.feature_names = list(X.columns)

        # 划分训练集和验证集
        X_train, X_val, y_train, y_val = train_test_split(X, y, test_size=0.2, random_state=42)

        # LightGBM参数
        params = {
            'objective': 'binary',
            'metric': 'binary_logloss',
            'boosting_type': 'gbdt',
            'num_leaves': 31,
            'learning_rate': 0.05,
            'feature_fraction': 0.8,
            'bagging_fraction': 0.8,
            'bagging_freq': 5,
            'verbose': -1,
            'random_state': 42
        }

        # 创建数据集
        train_data = lgb.Dataset(X_train, label=y_train)
        val_data = lgb.Dataset(X_val, label=y_val, reference=train_data)

        # 训练
        self.model = lgb.train(
            params,
            train_data,
            num_boost_round=200,
            valid_sets=[val_data],
            callbacks=[lgb.early_stopping(stopping_rounds=20), lgb.log_evaluation(period=0)]
        )

        # 评估
        y_pred = (self.model.predict(X_val) > 0.5).astype(int)
        accuracy = accuracy_score(y_val, y_pred)
        precision = precision_score(y_val, y_pred, average='weighted', zero_division=0)
        recall = recall_score(y_val, y_pred, average='weighted', zero_division=0)
        f1 = f1_score(y_val, y_pred, average='weighted', zero_division=0)

        logger.info(f"{self.instId} 模型训练完成 - "
                   f"准确率: {accuracy:.3f}, 精确率: {precision:.3f}, "
                   f"召回率: {recall:.3f}, F1: {f1:.3f}")

        # 特征重要性
        importance = self.model.feature_importance(importance_type='gain')
        feature_importance = sorted(zip(self.feature_names, importance), key=lambda x: x[1], reverse=True)
        logger.info(f"{self.instId} Top 10 重要特征:")
        for feature, imp in feature_importance[:10]:
            logger.info(f"  {feature}: {imp:.2f}")

        self.last_train_time = time.time()
        self.save()

    def predict(self, features: Dict) -> Tuple[int, float]:
        """
        预测

        Args:
            features: 特征字典

        Returns:
            (prediction, probability)
            prediction: 0=下跌, 1=上涨
            probability: 预测概率
        """
        if self.model is None or self.feature_names is None:
            return -1, 0.0

        # 构造特征向量
        X = pd.DataFrame([features])[self.feature_names].fillna(0)

        # 预测
        prob = self.model.predict(X)[0]
        prediction = 1 if prob > 0.5 else 0

        return prediction, prob

    def save(self):
        """保存模型"""
        model_data = {
            'model': self.model,
            'feature_names': self.feature_names,
            'last_train_time': self.last_train_time
        }

        with open(self.model_file, 'wb') as f:
            pickle.dump(model_data, f)

        logger.info(f"{self.instId} 模型已保存")

    def load(self):
        """加载模型"""
        if not os.path.exists(self.model_file):
            logger.info(f"{self.instId} 模型文件不存在，需要训练")
            return False

        try:
            with open(self.model_file, 'rb') as f:
                model_data = pickle.load(f)

            self.model = model_data['model']
            self.feature_names = model_data['feature_names']
            self.last_train_time = model_data.get('last_train_time', 0)

            logger.info(f"{self.instId} 模型加载成功，特征数: {len(self.feature_names)}")
            return True

        except Exception as e:
            logger.error(f"{self.instId} 模型加载失败: {e}")
            return False

    def should_retrain(self):
        """检查是否需要重新训练"""
        if self.model is None:
            return True

        if self.last_train_time is None:
            return True

        time_since_train = time.time() - self.last_train_time
        return time_since_train > MODEL_RETRAIN_INTERVAL

# ============================================================================
# 交易执行
# ============================================================================

def get_mark_price(instId):
    """获取市场价格"""
    try:
        response = market_api.get_ticker(instId)
        if 'data' in response and len(response['data']) > 0:
            return float(response['data'][0]['last'])
        return None
    except Exception as e:
        logger.error(f"{instId} 获取价格失败: {e}")
        return None

def round_price_to_tick(price, tick_size):
    """价格对齐到tick"""
    tick_decimals = len(f"{tick_size:.10f}".rstrip('0').split('.')[1]) if '.' in f"{tick_size:.10f}" else 0
    adjusted_price = round(price / tick_size) * tick_size
    return f"{adjusted_price:.{tick_decimals}f}"

def cancel_all_orders(instId):
    """取消所有挂单"""
    try:
        open_orders = trade_api.get_order_list(instId=instId, state='live')

        if 'code' in open_orders and open_orders['code'] != '0':
            return

        if 'data' not in open_orders or not open_orders['data']:
            return

        order_ids = [order['ordId'] for order in open_orders['data']]
        if not order_ids:
            return

        batch_size = 20
        for i in range(0, len(order_ids), batch_size):
            batch_ids = order_ids[i:i + batch_size]
            cancel_params = [{'instId': instId, 'ordId': ord_id} for ord_id in batch_ids]

            try:
                trade_api.cancel_multiple_orders(cancel_params)
            except:
                for ord_id in batch_ids:
                    try:
                        trade_api.cancel_order(instId=instId, ordId=ord_id)
                    except:
                        pass

    except Exception as e:
        logger.error(f"{instId} 取消订单失败: {e}")

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
        account_api.set_leverage(**body)
    except Exception as e:
        logger.error(f"{instId} 设置杠杆失败: {e}")

def place_order(instId, price, amount_usdt, side):
    """下单"""
    if instId not in instrument_info_dict:
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
            logger.info(f"{instId} 下单成功: {side} @ {adjusted_price}")

# ============================================================================
# 主策略逻辑
# ============================================================================

def process_pair_ml(instId: str, pair_config: Dict, ml_model: MLModel, data_collector: DataCollector):
    """基于机器学习的交易策略"""
    try:
        # 提取特征
        features = FeatureEngineer.extract_all_features(instId)
        if not features:
            logger.warning(f"{instId} 特征提取失败")
            return

        # 数据收集模式：只收集数据，不交易
        if DATA_COLLECTION_MODE:
            data_collector.collect_sample(features)
            data_collector.update_labels()
            data_collector.save()
            logger.info(f"{instId} 数据收集: 总样本数 {len(data_collector.data)}")
            return

        # 检查是否需要重新训练模型
        if ml_model.should_retrain():
            logger.info(f"{instId} 开始重新训练模型...")
            X, y = data_collector.get_training_data()
            if X is not None and y is not None:
                ml_model.train(X, y)

        # 模型预测
        prediction, probability = ml_model.predict(features)

        if prediction == -1:
            logger.warning(f"{instId} 模型未加载，跳过交易")
            return

        logger.info(f"{instId} ML预测: {'上涨' if prediction == 1 else '下跌'}, "
                   f"置信度: {probability:.2%}, "
                   f"OBI: {features.get('obi_10', 0):.3f}, "
                   f"Mid Price: {features.get('mid_price', 0):.2f}")

        # 根据预测概率决定是否交易
        if probability < PREDICTION_THRESHOLD and probability > (1 - PREDICTION_THRESHOLD):
            logger.info(f"{instId} 预测置信度不足，不交易")
            return

        # 取消旧订单
        cancel_all_orders(instId)

        # 获取配置
        amount_usdt = pair_config.get('long_amount_usdt', DEFAULT_AMOUNT_USDT)

        # 根据置信度调整金额
        confidence = abs(probability - 0.5) * 2  # 转换为0-1
        adjusted_amount = amount_usdt * confidence

        # 计算目标价格
        mid_price = features.get('mid_price', 0)
        spread = features.get('spread', 0)

        if prediction == 1 and probability > PREDICTION_THRESHOLD:
            # 预测上涨，挂买单
            target_price = mid_price - spread * 0.3
            place_order(instId, target_price, adjusted_amount, 'buy')

        elif prediction == 0 and probability < (1 - PREDICTION_THRESHOLD):
            # 预测下跌，挂卖单
            target_price = mid_price + spread * 0.3
            place_order(instId, target_price, adjusted_amount, 'sell')

        # 记录样本用于后续训练
        data_collector.collect_sample(features)

    except Exception as e:
        logger.error(f"{instId} 处理失败: {e}", exc_info=True)
        send_feishu_notification(f"{instId} ML策略异常: {e}")

def main():
    """主函数"""
    logger.info("=" * 60)
    logger.info("机器学习交易机器人启动")
    logger.info(f"监控间隔: {monitor_interval}秒")
    logger.info(f"数据收集模式: {DATA_COLLECTION_MODE}")
    logger.info(f"预测阈值: {PREDICTION_THRESHOLD}")
    logger.info("=" * 60)

    try:
        fetch_and_store_all_instruments()

        inst_ids = list(trading_pairs_config.keys())
        if not inst_ids:
            logger.error("配置文件中没有交易对")
            return

        # 为每个交易对创建模型和数据收集器
        models = {}
        collectors = {}

        for instId in inst_ids:
            models[instId] = MLModel(instId)
            collectors[instId] = DataCollector(instId)

        logger.info(f"已配置 {len(inst_ids)} 个交易对")

        loop_count = 0

        while True:
            loop_count += 1
            logger.info(f"\n{'='*60}")
            logger.info(f"第 {loop_count} 轮处理")
            logger.info(f"{'='*60}")

            try:
                for instId in inst_ids:
                    process_pair_ml(
                        instId,
                        trading_pairs_config[instId],
                        models[instId],
                        collectors[instId]
                    )

            except KeyboardInterrupt:
                logger.info("收到终止信号")
                break
            except Exception as e:
                logger.error(f"主循环异常: {e}", exc_info=True)

            logger.info(f"等待 {monitor_interval} 秒...\n")
            time.sleep(monitor_interval)

    except KeyboardInterrupt:
        logger.info("程序被用户中断")
    except Exception as e:
        logger.error(f"程序启动失败: {e}", exc_info=True)
    finally:
        logger.info("机器学习交易机器人已停止")

if __name__ == '__main__':
    main()
