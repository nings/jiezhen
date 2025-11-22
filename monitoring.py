"""
实时监控和预警系统
提供性能监控、异常检测和智能预警功能
"""
import time
import logging
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from collections import deque
import json

logger = logging.getLogger(__name__)


class AlertLevel(Enum):
    """预警级别"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class Alert:
    """预警"""
    level: AlertLevel
    message: str
    category: str  # 'performance', 'risk', 'system', 'market'
    timestamp: datetime = field(default_factory=datetime.now)
    acknowledged: bool = False
    metadata: Dict = field(default_factory=dict)


@dataclass
class PerformanceMetrics:
    """性能指标"""
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_profit: float = 0.0
    total_loss: float = 0.0
    max_profit: float = 0.0
    max_loss: float = 0.0
    avg_trade_duration: float = 0.0  # 秒
    sharpe_ratio: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0

    def calculate_derived_metrics(self):
        """计算衍生指标"""
        if self.total_trades > 0:
            self.win_rate = (self.winning_trades / self.total_trades) * 100

        if self.winning_trades > 0:
            self.avg_win = self.total_profit / self.winning_trades

        if self.losing_trades > 0:
            self.avg_loss = abs(self.total_loss) / self.losing_trades

        if abs(self.total_loss) > 0:
            self.profit_factor = self.total_profit / abs(self.total_loss)


@dataclass
class SystemMetrics:
    """系统指标"""
    api_calls_total: int = 0
    api_calls_failed: int = 0
    api_calls_retried: int = 0
    avg_response_time: float = 0.0  # 毫秒
    cache_hits: int = 0
    cache_misses: int = 0
    last_update: datetime = field(default_factory=datetime.now)


class PerformanceMonitor:
    """性能监控器"""

    def __init__(
        self,
        history_size: int = 1000,
        alert_callback: Optional[Callable] = None
    ):
        """
        初始化性能监控器

        Args:
            history_size: 历史数据保留大小
            alert_callback: 预警回调函数
        """
        self.history_size = history_size
        self.alert_callback = alert_callback

        self.metrics = PerformanceMetrics()
        self.system_metrics = SystemMetrics()
        self.alerts: deque = deque(maxlen=history_size)
        self.trade_history: deque = deque(maxlen=history_size)
        self.equity_curve: deque = deque(maxlen=history_size)

        # 监控阈值
        self.thresholds = {
            'max_consecutive_losses': 5,
            'max_drawdown_pct': 20.0,
            'min_win_rate': 30.0,
            'max_api_fail_rate': 10.0,
            'max_response_time_ms': 5000
        }

    def record_trade(
        self,
        inst_id: str,
        side: str,
        entry_price: float,
        exit_price: float,
        size_usdt: float,
        profit: float,
        duration_seconds: float
    ):
        """
        记录交易

        Args:
            inst_id: 交易对ID
            side: 方向
            entry_price: 入场价格
            exit_price: 出场价格
            size_usdt: 持仓大小
            profit: 盈亏
            duration_seconds: 持续时间
        """
        trade_record = {
            'inst_id': inst_id,
            'side': side,
            'entry_price': entry_price,
            'exit_price': exit_price,
            'size_usdt': size_usdt,
            'profit': profit,
            'duration': duration_seconds,
            'timestamp': datetime.now()
        }

        self.trade_history.append(trade_record)
        self.metrics.total_trades += 1

        if profit > 0:
            self.metrics.winning_trades += 1
            self.metrics.total_profit += profit
            self.metrics.max_profit = max(self.metrics.max_profit, profit)
        else:
            self.metrics.losing_trades += 1
            self.metrics.total_loss += profit
            self.metrics.max_loss = min(self.metrics.max_loss, profit)

        # 更新平均交易时长
        total_duration = (
            self.metrics.avg_trade_duration * (self.metrics.total_trades - 1) +
            duration_seconds
        )
        self.metrics.avg_trade_duration = total_duration / self.metrics.total_trades

        # 计算衍生指标
        self.metrics.calculate_derived_metrics()

        # 检查异常
        self._check_trade_anomalies()

        logger.info(
            f"{inst_id}: 交易已记录 - "
            f"{side}, 盈亏: {profit:.2f} USDT, "
            f"胜率: {self.metrics.win_rate:.1f}%"
        )

    def record_api_call(
        self,
        success: bool,
        response_time_ms: float,
        retried: bool = False
    ):
        """
        记录API调用

        Args:
            success: 是否成功
            response_time_ms: 响应时间（毫秒）
            retried: 是否重试
        """
        self.system_metrics.api_calls_total += 1

        if not success:
            self.system_metrics.api_calls_failed += 1

        if retried:
            self.system_metrics.api_calls_retried += 1

        # 更新平均响应时间
        total_time = (
            self.system_metrics.avg_response_time *
            (self.system_metrics.api_calls_total - 1) +
            response_time_ms
        )
        self.system_metrics.avg_response_time = (
            total_time / self.system_metrics.api_calls_total
        )

        self.system_metrics.last_update = datetime.now()

        # 检查API性能
        self._check_api_performance()

    def record_cache_hit(self, hit: bool):
        """记录缓存命中"""
        if hit:
            self.system_metrics.cache_hits += 1
        else:
            self.system_metrics.cache_misses += 1

    def update_equity(self, equity: float):
        """
        更新权益曲线

        Args:
            equity: 当前权益
        """
        self.equity_curve.append({
            'value': equity,
            'timestamp': datetime.now()
        })

        # 检查回撤
        self._check_drawdown()

    def _check_trade_anomalies(self):
        """检查交易异常"""
        # 检查连续亏损
        consecutive_losses = 0
        for trade in reversed(list(self.trade_history)):
            if trade['profit'] < 0:
                consecutive_losses += 1
            else:
                break

        if consecutive_losses >= self.thresholds['max_consecutive_losses']:
            self._create_alert(
                level=AlertLevel.WARNING,
                category='performance',
                message=f"连续亏损{consecutive_losses}次",
                metadata={'consecutive_losses': consecutive_losses}
            )

        # 检查胜率
        if (self.metrics.total_trades >= 20 and
            self.metrics.win_rate < self.thresholds['min_win_rate']):
            self._create_alert(
                level=AlertLevel.WARNING,
                category='performance',
                message=f"胜率过低: {self.metrics.win_rate:.1f}%",
                metadata={'win_rate': self.metrics.win_rate}
            )

    def _check_drawdown(self):
        """检查回撤"""
        if len(self.equity_curve) < 2:
            return

        equity_values = [e['value'] for e in self.equity_curve]
        peak = max(equity_values)
        current = equity_values[-1]

        if peak > 0:
            drawdown_pct = ((peak - current) / peak) * 100

            if drawdown_pct >= self.thresholds['max_drawdown_pct']:
                self._create_alert(
                    level=AlertLevel.CRITICAL,
                    category='risk',
                    message=f"回撤过大: {drawdown_pct:.1f}%",
                    metadata={
                        'drawdown_pct': drawdown_pct,
                        'peak': peak,
                        'current': current
                    }
                )

    def _check_api_performance(self):
        """检查API性能"""
        # 检查失败率
        if self.system_metrics.api_calls_total >= 10:
            fail_rate = (
                self.system_metrics.api_calls_failed /
                self.system_metrics.api_calls_total * 100
            )

            if fail_rate >= self.thresholds['max_api_fail_rate']:
                self._create_alert(
                    level=AlertLevel.ERROR,
                    category='system',
                    message=f"API失败率过高: {fail_rate:.1f}%",
                    metadata={'fail_rate': fail_rate}
                )

        # 检查响应时间
        if self.system_metrics.avg_response_time >= self.thresholds['max_response_time_ms']:
            self._create_alert(
                level=AlertLevel.WARNING,
                category='system',
                message=f"API响应时间过长: {self.system_metrics.avg_response_time:.0f}ms",
                metadata={'avg_response_time': self.system_metrics.avg_response_time}
            )

    def _create_alert(
        self,
        level: AlertLevel,
        category: str,
        message: str,
        metadata: Dict = None
    ):
        """创建预警"""
        alert = Alert(
            level=level,
            category=category,
            message=message,
            metadata=metadata or {}
        )

        self.alerts.append(alert)

        # 调用回调
        if self.alert_callback:
            try:
                self.alert_callback(alert)
            except Exception as e:
                logger.error(f"预警回调失败: {e}")

        # 记录日志
        log_func = {
            AlertLevel.INFO: logger.info,
            AlertLevel.WARNING: logger.warning,
            AlertLevel.ERROR: logger.error,
            AlertLevel.CRITICAL: logger.critical
        }[level]

        log_func(f"[{category.upper()}] {message}")

    def get_recent_alerts(
        self,
        minutes: int = 60,
        level: Optional[AlertLevel] = None
    ) -> List[Alert]:
        """
        获取最近的预警

        Args:
            minutes: 时间范围（分钟）
            level: 预警级别过滤

        Returns:
            预警列表
        """
        cutoff_time = datetime.now() - timedelta(minutes=minutes)
        alerts = [
            a for a in self.alerts
            if a.timestamp >= cutoff_time
        ]

        if level:
            alerts = [a for a in alerts if a.level == level]

        return alerts

    def get_performance_report(self) -> Dict:
        """
        获取性能报告

        Returns:
            性能报告字典
        """
        return {
            'total_trades': self.metrics.total_trades,
            'winning_trades': self.metrics.winning_trades,
            'losing_trades': self.metrics.losing_trades,
            'win_rate': f"{self.metrics.win_rate:.2f}%",
            'total_profit': f"{self.metrics.total_profit:.2f} USDT",
            'total_loss': f"{self.metrics.total_loss:.2f} USDT",
            'net_profit': f"{self.metrics.total_profit + self.metrics.total_loss:.2f} USDT",
            'profit_factor': f"{self.metrics.profit_factor:.2f}",
            'avg_win': f"{self.metrics.avg_win:.2f} USDT",
            'avg_loss': f"{self.metrics.avg_loss:.2f} USDT",
            'max_profit': f"{self.metrics.max_profit:.2f} USDT",
            'max_loss': f"{self.metrics.max_loss:.2f} USDT",
            'avg_trade_duration': f"{self.metrics.avg_trade_duration/60:.1f} min"
        }

    def get_system_report(self) -> Dict:
        """
        获取系统报告

        Returns:
            系统报告字典
        """
        cache_total = self.system_metrics.cache_hits + self.system_metrics.cache_misses
        cache_hit_rate = (
            self.system_metrics.cache_hits / cache_total * 100
            if cache_total > 0 else 0
        )

        api_fail_rate = (
            self.system_metrics.api_calls_failed /
            self.system_metrics.api_calls_total * 100
            if self.system_metrics.api_calls_total > 0 else 0
        )

        return {
            'api_calls_total': self.system_metrics.api_calls_total,
            'api_calls_failed': self.system_metrics.api_calls_failed,
            'api_fail_rate': f"{api_fail_rate:.2f}%",
            'api_calls_retried': self.system_metrics.api_calls_retried,
            'avg_response_time': f"{self.system_metrics.avg_response_time:.0f}ms",
            'cache_hit_rate': f"{cache_hit_rate:.1f}%",
            'cache_hits': self.system_metrics.cache_hits,
            'cache_misses': self.system_metrics.cache_misses
        }

    def export_metrics(self, filepath: str):
        """
        导出指标到文件

        Args:
            filepath: 文件路径
        """
        data = {
            'performance': self.get_performance_report(),
            'system': self.get_system_report(),
            'recent_alerts': [
                {
                    'level': a.level.value,
                    'category': a.category,
                    'message': a.message,
                    'timestamp': a.timestamp.isoformat()
                }
                for a in self.get_recent_alerts(minutes=1440)  # 最近24小时
            ],
            'export_time': datetime.now().isoformat()
        }

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info(f"指标已导出到 {filepath}")
        except Exception as e:
            logger.error(f"导出指标失败: {e}")

    def reset_metrics(self):
        """重置指标（通常在每日开始时调用）"""
        self.metrics = PerformanceMetrics()
        self.system_metrics = SystemMetrics()
        logger.info("指标已重置")
