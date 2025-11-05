"""
技术指标计算模块
提供各种技术指标的计算功能，支持缓存以提高性能
"""
from typing import List, Dict, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import pandas as pd


@dataclass
class IndicatorCache:
    """指标缓存数据结构"""
    value: float
    timestamp: datetime
    ttl_seconds: int = 60  # 缓存有效期（秒）

    def is_valid(self) -> bool:
        """检查缓存是否仍然有效"""
        return datetime.now() - self.timestamp < timedelta(seconds=self.ttl_seconds)


class TechnicalIndicators:
    """技术指标计算器（带缓存）"""

    def __init__(self, cache_ttl: int = 60):
        """
        初始化技术指标计算器

        Args:
            cache_ttl: 缓存有效期（秒）
        """
        self.cache_ttl = cache_ttl
        self._cache: Dict[str, IndicatorCache] = {}

    def _get_cache_key(self, inst_id: str, indicator: str, *args) -> str:
        """生成缓存键"""
        return f"{inst_id}:{indicator}:{':'.join(map(str, args))}"

    def _get_cached_value(self, cache_key: str) -> float | None:
        """获取缓存的指标值"""
        if cache_key in self._cache and self._cache[cache_key].is_valid():
            return self._cache[cache_key].value
        return None

    def _set_cache(self, cache_key: str, value: float):
        """设置缓存"""
        self._cache[cache_key] = IndicatorCache(
            value=value,
            timestamp=datetime.now(),
            ttl_seconds=self.cache_ttl
        )

    def calculate_ema(
        self,
        inst_id: str,
        close_prices: List[float],
        period: int,
        use_cache: bool = True
    ) -> float:
        """
        计算指数移动平均线（EMA）

        Args:
            inst_id: 交易对ID
            close_prices: 收盘价列表（时间顺序：旧→新）
            period: EMA周期
            use_cache: 是否使用缓存

        Returns:
            EMA值
        """
        cache_key = self._get_cache_key(inst_id, 'ema', period, close_prices[-1])

        if use_cache:
            cached_value = self._get_cached_value(cache_key)
            if cached_value is not None:
                return cached_value

        df = pd.Series(close_prices)
        ema = df.ewm(span=period, adjust=False).mean()
        result = float(ema.iloc[-1])

        if use_cache:
            self._set_cache(cache_key, result)

        return result

    def calculate_atr(
        self,
        inst_id: str,
        klines: List[List],
        period: int = 60,
        use_cache: bool = True
    ) -> float:
        """
        计算平均真实波幅（ATR）

        Args:
            inst_id: 交易对ID
            klines: K线数据（格式：[timestamp, open, high, low, close, ...]）
            period: ATR周期
            use_cache: 是否使用缓存

        Returns:
            ATR值
        """
        cache_key = self._get_cache_key(inst_id, 'atr', period, klines[0][0])

        if use_cache:
            cached_value = self._get_cached_value(cache_key)
            if cached_value is not None:
                return cached_value

        trs = []
        for i in range(1, len(klines)):
            high = float(klines[i][2])
            low = float(klines[i][3])
            prev_close = float(klines[i-1][4])

            # TR = max(H-L, |H-PC|, |L-PC|)
            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
            trs.append(tr)

        # 计算最近period根K线的平均TR
        result = sum(trs[-period:]) / period

        if use_cache:
            self._set_cache(cache_key, result)

        return result

    def calculate_average_amplitude(
        self,
        inst_id: str,
        klines: List[List],
        period: int = 60,
        use_cache: bool = True
    ) -> float:
        """
        计算平均振幅（百分比）

        Args:
            inst_id: 交易对ID
            klines: K线数据
            period: 计算周期
            use_cache: 是否使用缓存

        Returns:
            平均振幅（百分比）
        """
        cache_key = self._get_cache_key(inst_id, 'amplitude', period, klines[0][0])

        if use_cache:
            cached_value = self._get_cached_value(cache_key)
            if cached_value is not None:
                return cached_value

        amplitudes = []
        for i in range(len(klines) - period, len(klines)):
            high = float(klines[i][2])
            low = float(klines[i][3])
            close = float(klines[i][4])

            # 振幅 = (最高价 - 最低价) / 收盘价 * 100
            amplitude = ((high - low) / close) * 100
            amplitudes.append(amplitude)

        result = sum(amplitudes) / len(amplitudes)

        if use_cache:
            self._set_cache(cache_key, result)

        return result

    def calculate_price_atr_ratio(
        self,
        price: float,
        atr: float
    ) -> float:
        """
        计算价格/ATR比值（百分比）

        Args:
            price: 当前价格
            atr: ATR值

        Returns:
            价格/ATR比值（百分比）
        """
        if atr == 0:
            return 0
        return (price / atr) / 100

    def clear_cache(self, inst_id: str = None):
        """
        清除缓存

        Args:
            inst_id: 如果指定，只清除该交易对的缓存；否则清除全部缓存
        """
        if inst_id:
            keys_to_remove = [k for k in self._cache.keys() if k.startswith(f"{inst_id}:")]
            for key in keys_to_remove:
                del self._cache[key]
        else:
            self._cache.clear()

    def get_cache_stats(self) -> Dict[str, int]:
        """
        获取缓存统计信息

        Returns:
            包含缓存统计的字典
        """
        total = len(self._cache)
        valid = sum(1 for cache in self._cache.values() if cache.is_valid())
        return {
            'total': total,
            'valid': valid,
            'expired': total - valid
        }


class TrendAnalyzer:
    """趋势分析器"""

    @staticmethod
    def analyze_trend(
        current_price: float,
        ema: float,
        ema_enabled: bool = True
    ) -> Tuple[bool, bool]:
        """
        分析市场趋势

        Args:
            current_price: 当前价格
            ema: EMA值
            ema_enabled: 是否启用EMA（如果为False，则允许双向交易）

        Returns:
            (is_bullish, is_bearish) 元组
        """
        if not ema_enabled or ema == 0:
            # EMA未启用时，允许双向交易
            return True, True

        is_bullish = current_price > ema  # 多头趋势
        is_bearish = current_price < ema  # 空头趋势

        return is_bullish, is_bearish

    @staticmethod
    def get_trend_strength(
        current_price: float,
        ema: float
    ) -> float:
        """
        计算趋势强度（百分比）

        Args:
            current_price: 当前价格
            ema: EMA值

        Returns:
            趋势强度（正值表示多头，负值表示空头）
        """
        if ema == 0:
            return 0.0
        return ((current_price - ema) / ema) * 100
