"""
机器学习价格预测模块
使用技术指标预测短期价格走势
"""
import numpy as np
import logging
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
import pickle
import json
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
    from sklearn.preprocessing import StandardScaler
    from sklearn.model_selection import train_test_split
    ML_AVAILABLE = True
except ImportError:
    logger.warning("scikit-learn未安装，ML预测功能将被禁用")
    ML_AVAILABLE = False


@dataclass
class PredictionResult:
    """预测结果"""
    direction: str  # 'bullish', 'bearish', 'neutral'
    confidence: float  # 0-1之间
    probabilities: Dict[str, float]  # 各方向的概率
    features: Dict[str, float]  # 输入特征
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


class FeatureExtractor:
    """特征提取器"""

    @staticmethod
    def extract_features(
        klines: List[List],
        current_price: float,
        ema: float,
        atr: float,
        amplitude: float
    ) -> Dict[str, float]:
        """
        从K线数据和技术指标提取特征

        Args:
            klines: K线数据
            current_price: 当前价格
            ema: EMA值
            atr: ATR值
            amplitude: 平均振幅

        Returns:
            特征字典
        """
        features = {}

        # 1. 价格相关特征
        if ema > 0:
            features['price_ema_ratio'] = (current_price - ema) / ema * 100
        else:
            features['price_ema_ratio'] = 0

        features['atr_ratio'] = (atr / current_price) * 100 if current_price > 0 else 0
        features['amplitude'] = amplitude

        # 2. 趋势特征（最近N根K线）
        recent_klines = klines[:20]  # 最近20根
        closes = [float(k[4]) for k in recent_klines]

        if len(closes) >= 5:
            # 短期趋势（5根K线）
            features['trend_5'] = (closes[0] - closes[4]) / closes[4] * 100 if closes[4] > 0 else 0

            # 中期趋势（10根K线）
            if len(closes) >= 10:
                features['trend_10'] = (closes[0] - closes[9]) / closes[9] * 100 if closes[9] > 0 else 0

            # 长期趋势（20根K线）
            if len(closes) >= 20:
                features['trend_20'] = (closes[0] - closes[19]) / closes[19] * 100 if closes[19] > 0 else 0

        # 3. 波动率特征
        if len(closes) >= 10:
            returns = [(closes[i] - closes[i+1]) / closes[i+1] for i in range(len(closes)-1)]
            features['volatility'] = np.std(returns) * 100

        # 4. 动量特征
        if len(closes) >= 3:
            # RSI简化版（基于涨跌次数）
            ups = sum(1 for i in range(len(closes)-1) if closes[i] > closes[i+1])
            features['momentum'] = ups / (len(closes) - 1) * 100

        # 5. 成交量特征（如果有）
        volumes = [float(k[5]) for k in recent_klines if len(k) > 5]
        if len(volumes) >= 5:
            avg_volume = np.mean(volumes)
            current_volume = volumes[0]
            features['volume_ratio'] = (current_volume / avg_volume) if avg_volume > 0 else 1

        # 6. K线形态特征
        if len(recent_klines) >= 3:
            for i, k in enumerate(recent_klines[:3]):
                open_price = float(k[1])
                high = float(k[2])
                low = float(k[3])
                close = float(k[4])

                # K线实体
                body = abs(close - open_price)
                # 上下影线
                upper_shadow = high - max(close, open_price)
                lower_shadow = min(close, open_price) - low

                if close > 0:
                    features[f'candle_{i}_body_ratio'] = (body / close) * 100
                    features[f'candle_{i}_upper_shadow'] = (upper_shadow / close) * 100
                    features[f'candle_{i}_lower_shadow'] = (lower_shadow / close) * 100

        return features


class MLPredictor:
    """机器学习预测器"""

    def __init__(
        self,
        model_type: str = 'random_forest',
        model_path: str = 'models',
        confidence_threshold: float = 0.6
    ):
        """
        初始化ML预测器

        Args:
            model_type: 模型类型（'random_forest'或'gradient_boosting'）
            model_path: 模型保存路径
            confidence_threshold: 置信度阈值
        """
        self.model_type = model_type
        self.model_path = Path(model_path)
        self.model_path.mkdir(exist_ok=True)
        self.confidence_threshold = confidence_threshold
        self.enabled = ML_AVAILABLE

        self.models: Dict[str, any] = {}  # 每个交易对一个模型
        self.scalers: Dict[str, any] = {}  # 每个交易对一个标准化器
        self.feature_extractor = FeatureExtractor()

        if not self.enabled:
            logger.warning("ML预测器已禁用（scikit-learn未安装）")

    def _create_model(self):
        """创建新模型"""
        if not self.enabled:
            return None

        if self.model_type == 'random_forest':
            return RandomForestClassifier(
                n_estimators=100,
                max_depth=10,
                min_samples_split=5,
                random_state=42
            )
        elif self.model_type == 'gradient_boosting':
            return GradientBoostingClassifier(
                n_estimators=100,
                max_depth=5,
                learning_rate=0.1,
                random_state=42
            )
        else:
            raise ValueError(f"不支持的模型类型: {self.model_type}")

    def predict(
        self,
        inst_id: str,
        klines: List[List],
        current_price: float,
        ema: float,
        atr: float,
        amplitude: float
    ) -> Optional[PredictionResult]:
        """
        预测价格走势

        Args:
            inst_id: 交易对ID
            klines: K线数据
            current_price: 当前价格
            ema: EMA值
            atr: ATR值
            amplitude: 平均振幅

        Returns:
            预测结果或None（如果模型未训练）
        """
        if not self.enabled:
            return None

        # 检查模型是否存在
        if inst_id not in self.models:
            # 尝试加载模型
            if not self._load_model(inst_id):
                logger.debug(f"{inst_id}: 模型未训练，使用默认策略")
                return None

        # 提取特征
        features = self.feature_extractor.extract_features(
            klines, current_price, ema, atr, amplitude
        )

        # 转换为数组
        feature_names = sorted(features.keys())
        X = np.array([[features[name] for name in feature_names]])

        # 标准化
        if inst_id in self.scalers:
            X = self.scalers[inst_id].transform(X)

        # 预测
        try:
            probabilities = self.models[inst_id].predict_proba(X)[0]
            prediction = self.models[inst_id].predict(X)[0]

            # 类别映射：0=bearish, 1=neutral, 2=bullish
            classes = ['bearish', 'neutral', 'bullish']
            direction = classes[prediction]
            confidence = probabilities[prediction]

            prob_dict = {
                classes[i]: float(probabilities[i])
                for i in range(len(classes))
            }

            return PredictionResult(
                direction=direction,
                confidence=float(confidence),
                probabilities=prob_dict,
                features=features
            )

        except Exception as e:
            logger.error(f"{inst_id}: 预测失败 - {e}")
            return None

    def _load_model(self, inst_id: str) -> bool:
        """加载模型"""
        model_file = self.model_path / f"{inst_id.replace('-', '_')}_model.pkl"
        scaler_file = self.model_path / f"{inst_id.replace('-', '_')}_scaler.pkl"

        if not model_file.exists():
            return False

        try:
            with open(model_file, 'rb') as f:
                self.models[inst_id] = pickle.load(f)

            if scaler_file.exists():
                with open(scaler_file, 'rb') as f:
                    self.scalers[inst_id] = pickle.load(f)

            logger.info(f"{inst_id}: 模型加载成功")
            return True

        except Exception as e:
            logger.error(f"{inst_id}: 模型加载失败 - {e}")
            return False

    def train(
        self,
        inst_id: str,
        training_data: List[Dict],
        save_model: bool = True
    ) -> bool:
        """
        训练模型

        Args:
            inst_id: 交易对ID
            training_data: 训练数据列表，每个元素包含：
                - features: 特征字典
                - label: 标签（0=下跌, 1=中性, 2=上涨）
            save_model: 是否保存模型

        Returns:
            是否训练成功
        """
        if not self.enabled:
            logger.warning("ML不可用，无法训练模型")
            return False

        if len(training_data) < 100:
            logger.warning(f"{inst_id}: 训练数据不足（需要至少100条）")
            return False

        try:
            # 准备数据
            feature_names = sorted(training_data[0]['features'].keys())
            X = np.array([
                [d['features'][name] for name in feature_names]
                for d in training_data
            ])
            y = np.array([d['label'] for d in training_data])

            # 标准化
            scaler = StandardScaler()
            X = scaler.fit_transform(X)

            # 分割数据
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.2, random_state=42
            )

            # 训练模型
            model = self._create_model()
            model.fit(X_train, y_train)

            # 评估
            train_score = model.score(X_train, y_train)
            test_score = model.score(X_test, y_test)

            logger.info(
                f"{inst_id}: 模型训练完成 - "
                f"训练集准确率: {train_score:.3f}, "
                f"测试集准确率: {test_score:.3f}"
            )

            # 保存模型
            self.models[inst_id] = model
            self.scalers[inst_id] = scaler

            if save_model:
                self._save_model(inst_id)

            return True

        except Exception as e:
            logger.error(f"{inst_id}: 模型训练失败 - {e}")
            return False

    def _save_model(self, inst_id: str):
        """保存模型"""
        model_file = self.model_path / f"{inst_id.replace('-', '_')}_model.pkl"
        scaler_file = self.model_path / f"{inst_id.replace('-', '_')}_scaler.pkl"

        try:
            with open(model_file, 'wb') as f:
                pickle.dump(self.models[inst_id], f)

            with open(scaler_file, 'wb') as f:
                pickle.dump(self.scalers[inst_id], f)

            logger.info(f"{inst_id}: 模型已保存")

        except Exception as e:
            logger.error(f"{inst_id}: 模型保存失败 - {e}")


class SimplePredictor:
    """简单预测器（当ML不可用时的备选方案）"""

    def __init__(self):
        """初始化简单预测器"""
        self.feature_extractor = FeatureExtractor()

    def predict(
        self,
        inst_id: str,
        klines: List[List],
        current_price: float,
        ema: float,
        atr: float,
        amplitude: float
    ) -> PredictionResult:
        """
        基于规则的简单预测

        Returns:
            预测结果
        """
        features = self.feature_extractor.extract_features(
            klines, current_price, ema, atr, amplitude
        )

        # 简单规则
        score = 0

        # 趋势得分
        if ema > 0:
            if current_price > ema:
                score += 1
            else:
                score -= 1

        # 短期动量
        if 'trend_5' in features:
            if features['trend_5'] > 0.5:
                score += 1
            elif features['trend_5'] < -0.5:
                score -= 1

        # 判断方向
        if score > 0:
            direction = 'bullish'
            confidence = min(score / 3, 1.0)
            probabilities = {
                'bullish': confidence,
                'neutral': 1 - confidence,
                'bearish': 0
            }
        elif score < 0:
            direction = 'bearish'
            confidence = min(abs(score) / 3, 1.0)
            probabilities = {
                'bullish': 0,
                'neutral': 1 - confidence,
                'bearish': confidence
            }
        else:
            direction = 'neutral'
            confidence = 0.5
            probabilities = {
                'bullish': 0.33,
                'neutral': 0.34,
                'bearish': 0.33
            }

        return PredictionResult(
            direction=direction,
            confidence=confidence,
            probabilities=probabilities,
            features=features
        )
