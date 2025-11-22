"""
增强风险控制模块
包含止损、止盈、动态仓位管理等高级风控功能
"""
import logging
from typing import Dict, Optional, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger(__name__)


class StopLossType(Enum):
    """止损类型"""
    FIXED = "fixed"  # 固定止损
    TRAILING = "trailing"  # 移动止损
    ATR_BASED = "atr_based"  # 基于ATR的止损


@dataclass
class StopLossConfig:
    """止损配置"""
    enabled: bool = True
    stop_loss_type: StopLossType = StopLossType.TRAILING
    fixed_percentage: float = 5.0  # 固定止损百分比
    trailing_percentage: float = 3.0  # 移动止损百分比
    atr_multiplier: float = 2.0  # ATR倍数


@dataclass
class TakeProfitConfig:
    """止盈配置"""
    enabled: bool = True
    target_percentage: float = 10.0  # 目标盈利百分比
    partial_take_profit: bool = True  # 是否部分止盈
    partial_percentage: float = 50.0  # 部分止盈比例


@dataclass
class PositionSizing:
    """仓位管理配置"""
    use_kelly_criterion: bool = False  # 是否使用凯利公式
    max_position_percentage: float = 20.0  # 最大仓位占比（账户资金%）
    risk_per_trade_percentage: float = 2.0  # 每笔交易风险（账户资金%）


@dataclass
class StopLossOrder:
    """止损订单"""
    inst_id: str
    entry_price: float
    stop_price: float
    current_price: float
    position_side: str  # 'long' or 'short'
    size_usdt: float
    highest_price: float = 0.0  # 最高价（用于移动止损）
    lowest_price: float = 0.0  # 最低价（用于移动止损）
    created_at: datetime = field(default_factory=datetime.now)
    triggered: bool = False


class AdvancedRiskManager:
    """增强风险管理器"""

    def __init__(
        self,
        account_balance: float = 10000.0,
        stop_loss_config: StopLossConfig = None,
        take_profit_config: TakeProfitConfig = None,
        position_sizing: PositionSizing = None
    ):
        """
        初始化高级风险管理器

        Args:
            account_balance: 账户余额
            stop_loss_config: 止损配置
            take_profit_config: 止盈配置
            position_sizing: 仓位管理配置
        """
        self.account_balance = account_balance
        self.stop_loss_config = stop_loss_config or StopLossConfig()
        self.take_profit_config = take_profit_config or TakeProfitConfig()
        self.position_sizing = position_sizing or PositionSizing()

        self.stop_loss_orders: Dict[str, StopLossOrder] = {}
        self.drawdown_tracker: Dict[str, float] = {}  # 回撤跟踪
        self.consecutive_losses: int = 0  # 连续亏损次数

    def calculate_position_size(
        self,
        inst_id: str,
        entry_price: float,
        stop_loss_price: float,
        win_rate: float = 0.5,
        avg_win_loss_ratio: float = 1.5
    ) -> float:
        """
        计算推荐仓位大小

        Args:
            inst_id: 交易对ID
            entry_price: 入场价格
            stop_loss_price: 止损价格
            win_rate: 胜率（0-1）
            avg_win_loss_ratio: 平均盈亏比

        Returns:
            推荐仓位大小（USDT）
        """
        # 计算每单位风险
        risk_per_unit = abs(entry_price - stop_loss_price) / entry_price

        if risk_per_unit == 0:
            logger.warning(f"{inst_id}: 风险为0，使用默认仓位")
            return self.account_balance * 0.02

        # 凯利公式计算最优仓位
        if self.position_sizing.use_kelly_criterion:
            # Kelly = (Win% * Avg Win/Loss Ratio - Loss%) / Avg Win/Loss Ratio
            kelly_fraction = (
                win_rate * avg_win_loss_ratio - (1 - win_rate)
            ) / avg_win_loss_ratio

            # 保守起见，使用半凯利
            kelly_fraction = max(0, min(kelly_fraction * 0.5, 0.25))

            position_size = self.account_balance * kelly_fraction
        else:
            # 基于固定风险百分比
            risk_amount = self.account_balance * (
                self.position_sizing.risk_per_trade_percentage / 100
            )
            position_size = risk_amount / risk_per_unit

        # 限制最大仓位
        max_position = self.account_balance * (
            self.position_sizing.max_position_percentage / 100
        )
        position_size = min(position_size, max_position)

        logger.info(
            f"{inst_id}: 计算仓位大小 = {position_size:.2f} USDT "
            f"(风险{risk_per_unit*100:.2f}%)"
        )

        return position_size

    def calculate_stop_loss_price(
        self,
        inst_id: str,
        entry_price: float,
        position_side: str,
        atr: float = None
    ) -> float:
        """
        计算止损价格

        Args:
            inst_id: 交易对ID
            entry_price: 入场价格
            position_side: 持仓方向（'long'/'short'）
            atr: ATR值（如果使用ATR止损）

        Returns:
            止损价格
        """
        if not self.stop_loss_config.enabled:
            return 0.0

        if self.stop_loss_config.stop_loss_type == StopLossType.FIXED:
            # 固定百分比止损
            percentage = self.stop_loss_config.fixed_percentage / 100
            if position_side == 'long':
                return entry_price * (1 - percentage)
            else:
                return entry_price * (1 + percentage)

        elif self.stop_loss_config.stop_loss_type == StopLossType.ATR_BASED:
            # 基于ATR的止损
            if atr is None or atr == 0:
                logger.warning(f"{inst_id}: ATR未提供，使用固定止损")
                percentage = self.stop_loss_config.fixed_percentage / 100
                if position_side == 'long':
                    return entry_price * (1 - percentage)
                else:
                    return entry_price * (1 + percentage)

            atr_distance = atr * self.stop_loss_config.atr_multiplier
            if position_side == 'long':
                return entry_price - atr_distance
            else:
                return entry_price + atr_distance

        else:  # TRAILING
            # 初始移动止损价格
            percentage = self.stop_loss_config.trailing_percentage / 100
            if position_side == 'long':
                return entry_price * (1 - percentage)
            else:
                return entry_price * (1 + percentage)

    def add_stop_loss_order(
        self,
        inst_id: str,
        entry_price: float,
        position_side: str,
        size_usdt: float,
        atr: float = None
    ):
        """
        添加止损订单

        Args:
            inst_id: 交易对ID
            entry_price: 入场价格
            position_side: 持仓方向
            size_usdt: 持仓大小
            atr: ATR值
        """
        stop_price = self.calculate_stop_loss_price(
            inst_id, entry_price, position_side, atr
        )

        order = StopLossOrder(
            inst_id=inst_id,
            entry_price=entry_price,
            stop_price=stop_price,
            current_price=entry_price,
            position_side=position_side,
            size_usdt=size_usdt,
            highest_price=entry_price,
            lowest_price=entry_price
        )

        self.stop_loss_orders[inst_id] = order

        logger.info(
            f"{inst_id}: 止损订单已添加 - "
            f"入场价: {entry_price:.6f}, "
            f"止损价: {stop_price:.6f} "
            f"({position_side})"
        )

    def update_trailing_stop(
        self,
        inst_id: str,
        current_price: float
    ) -> Optional[float]:
        """
        更新移动止损

        Args:
            inst_id: 交易对ID
            current_price: 当前价格

        Returns:
            新的止损价格（如果更新）或None
        """
        if inst_id not in self.stop_loss_orders:
            return None

        order = self.stop_loss_orders[inst_id]
        order.current_price = current_price

        if self.stop_loss_config.stop_loss_type != StopLossType.TRAILING:
            return None

        # 更新最高/最低价
        order.highest_price = max(order.highest_price, current_price)
        order.lowest_price = min(order.lowest_price, current_price)

        percentage = self.stop_loss_config.trailing_percentage / 100
        new_stop_price = order.stop_price

        if order.position_side == 'long':
            # 多头：价格创新高时提高止损
            new_stop_price = order.highest_price * (1 - percentage)
            if new_stop_price > order.stop_price:
                order.stop_price = new_stop_price
                logger.info(
                    f"{inst_id}: 移动止损已更新 - "
                    f"新止损价: {new_stop_price:.6f}"
                )
                return new_stop_price
        else:
            # 空头：价格创新低时降低止损
            new_stop_price = order.lowest_price * (1 + percentage)
            if new_stop_price < order.stop_price:
                order.stop_price = new_stop_price
                logger.info(
                    f"{inst_id}: 移动止损已更新 - "
                    f"新止损价: {new_stop_price:.6f}"
                )
                return new_stop_price

        return None

    def check_stop_loss(
        self,
        inst_id: str,
        current_price: float
    ) -> Tuple[bool, str]:
        """
        检查是否触发止损

        Args:
            inst_id: 交易对ID
            current_price: 当前价格

        Returns:
            (是否触发, 原因)
        """
        if inst_id not in self.stop_loss_orders:
            return False, ""

        order = self.stop_loss_orders[inst_id]

        if order.position_side == 'long':
            if current_price <= order.stop_price:
                order.triggered = True
                loss_pct = ((current_price - order.entry_price) / order.entry_price) * 100
                reason = (
                    f"多头止损触发 - "
                    f"当前价: {current_price:.6f}, "
                    f"止损价: {order.stop_price:.6f}, "
                    f"亏损: {loss_pct:.2f}%"
                )
                logger.warning(f"{inst_id}: {reason}")
                return True, reason
        else:
            if current_price >= order.stop_price:
                order.triggered = True
                loss_pct = ((order.entry_price - current_price) / order.entry_price) * 100
                reason = (
                    f"空头止损触发 - "
                    f"当前价: {current_price:.6f}, "
                    f"止损价: {order.stop_price:.6f}, "
                    f"亏损: {loss_pct:.2f}%"
                )
                logger.warning(f"{inst_id}: {reason}")
                return True, reason

        return False, ""

    def check_take_profit(
        self,
        inst_id: str,
        entry_price: float,
        current_price: float,
        position_side: str
    ) -> Tuple[bool, float, str]:
        """
        检查是否触发止盈

        Args:
            inst_id: 交易对ID
            entry_price: 入场价格
            current_price: 当前价格
            position_side: 持仓方向

        Returns:
            (是否触发, 止盈比例%, 原因)
        """
        if not self.take_profit_config.enabled:
            return False, 0.0, ""

        profit_pct = 0.0
        if position_side == 'long':
            profit_pct = ((current_price - entry_price) / entry_price) * 100
        else:
            profit_pct = ((entry_price - current_price) / entry_price) * 100

        target_pct = self.take_profit_config.target_percentage

        if profit_pct >= target_pct:
            if self.take_profit_config.partial_take_profit:
                # 部分止盈
                partial_pct = self.take_profit_config.partial_percentage
                reason = (
                    f"部分止盈触发 ({partial_pct}%) - "
                    f"盈利: {profit_pct:.2f}%, "
                    f"目标: {target_pct:.2f}%"
                )
                logger.info(f"{inst_id}: {reason}")
                return True, partial_pct, reason
            else:
                # 全部止盈
                reason = (
                    f"止盈触发 - "
                    f"盈利: {profit_pct:.2f}%, "
                    f"目标: {target_pct:.2f}%"
                )
                logger.info(f"{inst_id}: {reason}")
                return True, 100.0, reason

        return False, 0.0, ""

    def calculate_max_drawdown(
        self,
        equity_curve: List[float]
    ) -> float:
        """
        计算最大回撤

        Args:
            equity_curve: 权益曲线

        Returns:
            最大回撤百分比
        """
        if not equity_curve or len(equity_curve) < 2:
            return 0.0

        peak = equity_curve[0]
        max_dd = 0.0

        for value in equity_curve:
            if value > peak:
                peak = value
            dd = (peak - value) / peak * 100
            max_dd = max(max_dd, dd)

        return max_dd

    def should_reduce_risk(self) -> Tuple[bool, str]:
        """
        判断是否应该降低风险

        Returns:
            (是否降低, 原因)
        """
        # 连续亏损保护
        if self.consecutive_losses >= 3:
            return True, f"连续亏损{self.consecutive_losses}次，建议降低仓位"

        # 账户余额检查
        if self.account_balance < 1000:
            return True, "账户余额过低，建议停止交易"

        return False, ""

    def record_trade_result(
        self,
        inst_id: str,
        profit: float
    ):
        """
        记录交易结果

        Args:
            inst_id: 交易对ID
            profit: 盈亏金额
        """
        self.account_balance += profit

        if profit < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0

        logger.info(
            f"{inst_id}: 交易结果记录 - "
            f"盈亏: {profit:.2f} USDT, "
            f"账户余额: {self.account_balance:.2f} USDT, "
            f"连续亏损: {self.consecutive_losses}"
        )

    def remove_stop_loss_order(self, inst_id: str):
        """移除止损订单"""
        if inst_id in self.stop_loss_orders:
            del self.stop_loss_orders[inst_id]
            logger.info(f"{inst_id}: 止损订单已移除")

    def get_risk_summary(self) -> Dict:
        """
        获取风险摘要

        Returns:
            风险摘要字典
        """
        return {
            'account_balance': self.account_balance,
            'active_stop_orders': len(self.stop_loss_orders),
            'consecutive_losses': self.consecutive_losses,
            'stop_loss_enabled': self.stop_loss_config.enabled,
            'take_profit_enabled': self.take_profit_config.enabled,
            'stop_loss_type': self.stop_loss_config.stop_loss_type.value
        }
