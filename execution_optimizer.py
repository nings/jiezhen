"""
订单执行优化模块
实现TWAP、VWAP等智能执行算法，减少市场冲击
"""
import time
import logging
from typing import List, Dict, Optional, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
import numpy as np

logger = logging.getLogger(__name__)


class ExecutionStrategy(Enum):
    """执行策略类型"""
    IMMEDIATE = "immediate"  # 立即执行
    TWAP = "twap"  # 时间加权平均价格
    VWAP = "vwap"  # 成交量加权平均价格
    ADAPTIVE = "adaptive"  # 自适应执行


@dataclass
class OrderSlice:
    """订单切片"""
    size: float  # 数量
    price: Optional[float] = None  # 价格（None表示市价）
    execute_at: datetime = None  # 执行时间
    executed: bool = False
    execution_time: Optional[datetime] = None
    execution_price: Optional[float] = None


@dataclass
class ExecutionPlan:
    """执行计划"""
    strategy: ExecutionStrategy
    total_size: float
    slices: List[OrderSlice]
    start_time: datetime
    end_time: datetime
    completed: bool = False


class ExecutionOptimizer:
    """订单执行优化器"""

    def __init__(
        self,
        min_slice_size: float = 10.0,  # 最小切片金额（USDT）
        max_slices: int = 10,  # 最大切片数量
        default_duration_minutes: int = 5  # 默认执行时长（分钟）
    ):
        """
        初始化执行优化器

        Args:
            min_slice_size: 最小切片金额
            max_slices: 最大切片数量
            default_duration_minutes: 默认执行时长
        """
        self.min_slice_size = min_slice_size
        self.max_slices = max_slices
        self.default_duration_minutes = default_duration_minutes
        self.active_plans: Dict[str, ExecutionPlan] = {}

    def should_split_order(
        self,
        amount_usdt: float,
        market_volatility: float = 1.0
    ) -> bool:
        """
        判断是否需要拆分订单

        Args:
            amount_usdt: 订单金额
            market_volatility: 市场波动率（0-10，越大越不稳定）

        Returns:
            是否需要拆分
        """
        # 大额订单或高波动市场需要拆分
        threshold = 100.0 / market_volatility  # 波动越大，阈值越低
        return amount_usdt > threshold

    def create_twap_plan(
        self,
        inst_id: str,
        total_amount: float,
        duration_minutes: int = None,
        num_slices: int = None
    ) -> ExecutionPlan:
        """
        创建TWAP执行计划（时间加权平均）

        Args:
            inst_id: 交易对ID
            total_amount: 总金额（USDT）
            duration_minutes: 执行时长（分钟）
            num_slices: 切片数量

        Returns:
            执行计划
        """
        if duration_minutes is None:
            duration_minutes = self.default_duration_minutes

        if num_slices is None:
            # 自动计算切片数量
            num_slices = min(
                int(total_amount / self.min_slice_size),
                self.max_slices,
                duration_minutes  # 每分钟最多一个切片
            )
            num_slices = max(num_slices, 1)

        # 计算每个切片的大小（均等）
        slice_size = total_amount / num_slices

        # 计算执行时间间隔
        interval_seconds = (duration_minutes * 60) / num_slices

        start_time = datetime.now()
        slices = []

        for i in range(num_slices):
            execute_at = start_time + timedelta(seconds=i * interval_seconds)
            slices.append(OrderSlice(
                size=slice_size,
                execute_at=execute_at
            ))

        plan = ExecutionPlan(
            strategy=ExecutionStrategy.TWAP,
            total_size=total_amount,
            slices=slices,
            start_time=start_time,
            end_time=start_time + timedelta(minutes=duration_minutes)
        )

        self.active_plans[inst_id] = plan
        logger.info(
            f"{inst_id}: TWAP计划已创建 - "
            f"{num_slices}个切片，总金额{total_amount:.2f} USDT，"
            f"执行时长{duration_minutes}分钟"
        )

        return plan

    def create_vwap_plan(
        self,
        inst_id: str,
        total_amount: float,
        volume_profile: List[float] = None,
        duration_minutes: int = None
    ) -> ExecutionPlan:
        """
        创建VWAP执行计划（成交量加权平均）

        Args:
            inst_id: 交易对ID
            total_amount: 总金额（USDT）
            volume_profile: 成交量分布（如果为None，使用默认分布）
            duration_minutes: 执行时长（分钟）

        Returns:
            执行计划
        """
        if duration_minutes is None:
            duration_minutes = self.default_duration_minutes

        # 默认成交量分布（假设U型分布：开盘和收盘时成交量大）
        if volume_profile is None:
            num_slices = min(self.max_slices, duration_minutes)
            # U型分布
            volume_profile = [
                1.5 if i < num_slices * 0.2 or i > num_slices * 0.8 else 1.0
                for i in range(num_slices)
            ]

        # 归一化成交量分布
        total_volume = sum(volume_profile)
        normalized_volumes = [v / total_volume for v in volume_profile]

        # 根据成交量分布计算每个切片的大小
        num_slices = len(volume_profile)
        interval_seconds = (duration_minutes * 60) / num_slices

        start_time = datetime.now()
        slices = []

        for i, volume_weight in enumerate(normalized_volumes):
            slice_size = total_amount * volume_weight
            if slice_size < self.min_slice_size and i < num_slices - 1:
                # 太小的切片合并到下一个
                continue

            execute_at = start_time + timedelta(seconds=i * interval_seconds)
            slices.append(OrderSlice(
                size=slice_size,
                execute_at=execute_at
            ))

        plan = ExecutionPlan(
            strategy=ExecutionStrategy.VWAP,
            total_size=total_amount,
            slices=slices,
            start_time=start_time,
            end_time=start_time + timedelta(minutes=duration_minutes)
        )

        self.active_plans[inst_id] = plan
        logger.info(
            f"{inst_id}: VWAP计划已创建 - "
            f"{len(slices)}个切片，总金额{total_amount:.2f} USDT"
        )

        return plan

    def create_adaptive_plan(
        self,
        inst_id: str,
        total_amount: float,
        current_spread: float,
        avg_spread: float,
        duration_minutes: int = None
    ) -> ExecutionPlan:
        """
        创建自适应执行计划（根据市场条件动态调整）

        Args:
            inst_id: 交易对ID
            total_amount: 总金额
            current_spread: 当前买卖价差
            avg_spread: 平均买卖价差
            duration_minutes: 执行时长

        Returns:
            执行计划
        """
        if duration_minutes is None:
            duration_minutes = self.default_duration_minutes

        # 根据价差判断市场流动性
        spread_ratio = current_spread / avg_spread if avg_spread > 0 else 1.0

        if spread_ratio > 2.0:
            # 流动性差，使用更多切片，执行时间更长
            num_slices = self.max_slices
            duration_minutes = int(duration_minutes * 1.5)
        elif spread_ratio > 1.5:
            # 流动性一般
            num_slices = self.max_slices // 2
        else:
            # 流动性好，可以更快执行
            num_slices = max(self.max_slices // 3, 2)
            duration_minutes = int(duration_minutes * 0.7)

        # 使用TWAP作为基础
        return self.create_twap_plan(
            inst_id, total_amount, duration_minutes, num_slices
        )

    def get_next_slice(
        self,
        inst_id: str
    ) -> Optional[OrderSlice]:
        """
        获取下一个应该执行的切片

        Args:
            inst_id: 交易对ID

        Returns:
            订单切片或None
        """
        if inst_id not in self.active_plans:
            return None

        plan = self.active_plans[inst_id]
        now = datetime.now()

        for slice_order in plan.slices:
            if not slice_order.executed and slice_order.execute_at <= now:
                return slice_order

        return None

    def mark_slice_executed(
        self,
        inst_id: str,
        slice_order: OrderSlice,
        execution_price: float
    ):
        """
        标记切片已执行

        Args:
            inst_id: 交易对ID
            slice_order: 订单切片
            execution_price: 执行价格
        """
        slice_order.executed = True
        slice_order.execution_time = datetime.now()
        slice_order.execution_price = execution_price

        # 检查计划是否全部完成
        if inst_id in self.active_plans:
            plan = self.active_plans[inst_id]
            if all(s.executed for s in plan.slices):
                plan.completed = True
                logger.info(f"{inst_id}: 执行计划已完成")

    def get_execution_stats(
        self,
        inst_id: str
    ) -> Optional[Dict]:
        """
        获取执行统计

        Args:
            inst_id: 交易对ID

        Returns:
            统计信息字典
        """
        if inst_id not in self.active_plans:
            return None

        plan = self.active_plans[inst_id]
        executed_slices = [s for s in plan.slices if s.executed]

        if not executed_slices:
            return {
                'progress': 0.0,
                'executed_amount': 0.0,
                'avg_price': 0.0
            }

        executed_amount = sum(s.size for s in executed_slices)
        avg_price = np.average(
            [s.execution_price for s in executed_slices],
            weights=[s.size for s in executed_slices]
        )

        return {
            'strategy': plan.strategy.value,
            'progress': (executed_amount / plan.total_size) * 100,
            'executed_amount': executed_amount,
            'total_amount': plan.total_size,
            'avg_price': avg_price,
            'num_slices': len(plan.slices),
            'executed_slices': len(executed_slices),
            'completed': plan.completed
        }

    def cancel_plan(self, inst_id: str):
        """
        取消执行计划

        Args:
            inst_id: 交易对ID
        """
        if inst_id in self.active_plans:
            del self.active_plans[inst_id]
            logger.info(f"{inst_id}: 执行计划已取消")

    def cleanup_completed_plans(self):
        """清理已完成的计划"""
        completed = [
            inst_id for inst_id, plan in self.active_plans.items()
            if plan.completed
        ]
        for inst_id in completed:
            del self.active_plans[inst_id]

        if completed:
            logger.info(f"已清理{len(completed)}个完成的执行计划")
