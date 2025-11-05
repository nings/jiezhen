"""
风险管理模块
提供风险控制和资金管理功能
"""
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    """风险等级"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class PositionInfo:
    """持仓信息"""
    inst_id: str
    side: str  # 'long' or 'short'
    size_usdt: float
    entry_price: float
    current_price: float
    pnl_usdt: float
    leverage: int
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def pnl_percentage(self) -> float:
        """计算盈亏百分比"""
        if self.entry_price == 0:
            return 0
        if self.side == 'long':
            return ((self.current_price - self.entry_price) / self.entry_price) * 100
        else:
            return ((self.entry_price - self.current_price) / self.entry_price) * 100


@dataclass
class DailyStats:
    """每日统计"""
    date: str
    total_pnl: float = 0.0
    trades_count: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    max_drawdown: float = 0.0

    @property
    def win_rate(self) -> float:
        """胜率"""
        if self.trades_count == 0:
            return 0
        return (self.winning_trades / self.trades_count) * 100


class RiskManager:
    """风险管理器"""

    def __init__(
        self,
        max_position_size_usdt: float = 1000.0,
        max_total_position_usdt: float = 5000.0,
        max_daily_loss_usdt: float = 500.0,
        max_orders_per_pair: int = 2,
        enable_risk_control: bool = True
    ):
        """
        初始化风险管理器

        Args:
            max_position_size_usdt: 单个交易对最大持仓（USDT）
            max_total_position_usdt: 总持仓限制（USDT）
            max_daily_loss_usdt: 单日最大亏损
            max_orders_per_pair: 每个交易对最大挂单数
            enable_risk_control: 是否启用风险控制
        """
        self.max_position_size_usdt = max_position_size_usdt
        self.max_total_position_usdt = max_total_position_usdt
        self.max_daily_loss_usdt = max_daily_loss_usdt
        self.max_orders_per_pair = max_orders_per_pair
        self.enable_risk_control = enable_risk_control

        self.positions: Dict[str, PositionInfo] = {}
        self.daily_stats: Dict[str, DailyStats] = {}
        self.daily_pnl: float = 0.0
        self.order_count: Dict[str, int] = {}

    def can_place_order(
        self,
        inst_id: str,
        amount_usdt: float,
        side: str
    ) -> tuple[bool, str]:
        """
        检查是否可以下单

        Args:
            inst_id: 交易对ID
            amount_usdt: 下单金额（USDT）
            side: 方向（'buy'/'sell'）

        Returns:
            (可以下单, 原因) 元组
        """
        if not self.enable_risk_control:
            return True, "风险控制已禁用"

        # 检查单日亏损限制
        if self.daily_pnl < -self.max_daily_loss_usdt:
            return False, f"已达到单日最大亏损限制 ({self.daily_pnl:.2f} USDT)"

        # 检查单个交易对持仓限制
        current_position = self._get_position_size(inst_id)
        if current_position + amount_usdt > self.max_position_size_usdt:
            return False, f"超过单个交易对持仓限制 (当前: {current_position:.2f}, 限制: {self.max_position_size_usdt})"

        # 检查总持仓限制
        total_position = self._get_total_position_size()
        if total_position + amount_usdt > self.max_total_position_usdt:
            return False, f"超过总持仓限制 (当前: {total_position:.2f}, 限制: {self.max_total_position_usdt})"

        # 检查每个交易对的挂单数量
        order_count = self.order_count.get(inst_id, 0)
        if order_count >= self.max_orders_per_pair:
            return False, f"超过单个交易对最大挂单数 (当前: {order_count}, 限制: {self.max_orders_per_pair})"

        return True, "检查通过"

    def record_order(self, inst_id: str):
        """记录下单"""
        self.order_count[inst_id] = self.order_count.get(inst_id, 0) + 1

    def clear_orders(self, inst_id: str):
        """清除交易对的挂单计数"""
        self.order_count[inst_id] = 0

    def update_position(
        self,
        inst_id: str,
        side: str,
        size_usdt: float,
        entry_price: float,
        current_price: float,
        pnl_usdt: float,
        leverage: int
    ):
        """
        更新持仓信息

        Args:
            inst_id: 交易对ID
            side: 方向
            size_usdt: 持仓大小（USDT）
            entry_price: 开仓价格
            current_price: 当前价格
            pnl_usdt: 盈亏（USDT）
            leverage: 杠杆倍数
        """
        position = PositionInfo(
            inst_id=inst_id,
            side=side,
            size_usdt=size_usdt,
            entry_price=entry_price,
            current_price=current_price,
            pnl_usdt=pnl_usdt,
            leverage=leverage
        )
        self.positions[inst_id] = position

    def remove_position(self, inst_id: str):
        """移除持仓"""
        if inst_id in self.positions:
            del self.positions[inst_id]

    def update_daily_pnl(self, pnl: float):
        """更新每日盈亏"""
        self.daily_pnl += pnl

        # 更新每日统计
        today = datetime.now().strftime("%Y-%m-%d")
        if today not in self.daily_stats:
            self.daily_stats[today] = DailyStats(date=today)

        stats = self.daily_stats[today]
        stats.total_pnl += pnl
        stats.trades_count += 1

        if pnl > 0:
            stats.winning_trades += 1
        elif pnl < 0:
            stats.losing_trades += 1

    def reset_daily_stats(self):
        """重置每日统计（每天执行一次）"""
        self.daily_pnl = 0.0
        # 保留历史统计数据

    def _get_position_size(self, inst_id: str) -> float:
        """获取指定交易对的持仓大小"""
        if inst_id in self.positions:
            return self.positions[inst_id].size_usdt
        return 0.0

    def _get_total_position_size(self) -> float:
        """获取总持仓大小"""
        return sum(pos.size_usdt for pos in self.positions.values())

    def get_risk_level(self) -> RiskLevel:
        """
        获取当前风险等级

        Returns:
            风险等级
        """
        if not self.enable_risk_control:
            return RiskLevel.LOW

        total_position = self._get_total_position_size()
        position_ratio = total_position / self.max_total_position_usdt

        daily_loss_ratio = abs(self.daily_pnl) / self.max_daily_loss_usdt if self.daily_pnl < 0 else 0

        if position_ratio > 0.9 or daily_loss_ratio > 0.9:
            return RiskLevel.CRITICAL
        elif position_ratio > 0.7 or daily_loss_ratio > 0.7:
            return RiskLevel.HIGH
        elif position_ratio > 0.5 or daily_loss_ratio > 0.5:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.LOW

    def get_risk_metrics(self) -> Dict:
        """
        获取风险指标

        Returns:
            风险指标字典
        """
        total_position = self._get_total_position_size()
        return {
            'total_position_usdt': total_position,
            'position_utilization': (total_position / self.max_total_position_usdt) * 100,
            'daily_pnl_usdt': self.daily_pnl,
            'daily_loss_utilization': (abs(self.daily_pnl) / self.max_daily_loss_usdt) * 100 if self.daily_pnl < 0 else 0,
            'risk_level': self.get_risk_level().value,
            'positions_count': len(self.positions),
            'active_orders_count': sum(self.order_count.values())
        }

    def should_stop_trading(self) -> tuple[bool, str]:
        """
        判断是否应该停止交易

        Returns:
            (应该停止, 原因) 元组
        """
        if not self.enable_risk_control:
            return False, ""

        # 检查单日亏损
        if self.daily_pnl < -self.max_daily_loss_usdt:
            return True, f"单日亏损超过限制 ({self.daily_pnl:.2f} USDT)"

        # 检查总持仓
        total_position = self._get_total_position_size()
        if total_position >= self.max_total_position_usdt:
            return True, f"总持仓已达限制 ({total_position:.2f} USDT)"

        return False, ""

    def get_position_report(self) -> str:
        """
        生成持仓报告

        Returns:
            持仓报告文本
        """
        if not self.positions:
            return "当前无持仓"

        lines = ["=== 持仓报告 ==="]
        total_pnl = 0

        for inst_id, pos in self.positions.items():
            lines.append(
                f"{inst_id}: {pos.side} | "
                f"持仓: {pos.size_usdt:.2f} USDT | "
                f"盈亏: {pos.pnl_usdt:.2f} USDT ({pos.pnl_percentage:.2f}%)"
            )
            total_pnl += pos.pnl_usdt

        lines.append(f"总盈亏: {total_pnl:.2f} USDT")
        return "\n".join(lines)

    def get_daily_report(self, date: str = None) -> str:
        """
        生成每日报告

        Args:
            date: 日期（格式：YYYY-MM-DD），默认为今天

        Returns:
            每日报告文本
        """
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")

        if date not in self.daily_stats:
            return f"无 {date} 的交易数据"

        stats = self.daily_stats[date]
        return f"""
=== 每日报告 ({date}) ===
总盈亏: {stats.total_pnl:.2f} USDT
交易次数: {stats.trades_count}
盈利次数: {stats.winning_trades}
亏损次数: {stats.losing_trades}
胜率: {stats.win_rate:.2f}%
最大回撤: {stats.max_drawdown:.2f} USDT
""".strip()
