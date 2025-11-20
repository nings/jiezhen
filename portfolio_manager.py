#!/usr/bin/env python3
"""
多策略组合管理系统

功能：
- 策略注册和管理
- 动态资金分配
- 基于表现的再平衡
- 相关性分析
- 组合优化
- 策略组合框架
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
from scipy.optimize import minimize
import json

logger = logging.getLogger(__name__)


@dataclass
class StrategyConfig:
    """策略配置"""
    name: str
    strategy_type: str  # 'ml', 'orderbook', 'trend', etc.
    initial_allocation: float  # 初始资金分配比例
    min_allocation: float = 0.05  # 最小分配比例
    max_allocation: float = 0.50  # 最大分配比例
    enabled: bool = True


@dataclass
class StrategyPerformance:
    """策略表现"""
    name: str
    total_return: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    total_trades: int = 0
    avg_trade_pnl: float = 0.0
    current_capital: float = 0.0
    equity_curve: List[float] = field(default_factory=list)
    returns: List[float] = field(default_factory=list)


class StrategyAllocation:
    """策略分配器"""

    def __init__(self, total_capital: float):
        """
        初始化分配器

        Args:
            total_capital: 总资金
        """
        self.total_capital = total_capital
        self.strategies: Dict[str, StrategyConfig] = {}
        self.allocations: Dict[str, float] = {}  # 当前分配金额
        self.performance_history: Dict[str, StrategyPerformance] = {}

    def register_strategy(self, config: StrategyConfig):
        """
        注册策略

        Args:
            config: 策略配置
        """
        self.strategies[config.name] = config
        self.allocations[config.name] = self.total_capital * config.initial_allocation
        self.performance_history[config.name] = StrategyPerformance(name=config.name)

        logger.info(f"策略已注册: {config.name}, 初始分配: ${self.allocations[config.name]:.2f}")

    def update_strategy_performance(self, name: str, performance: StrategyPerformance):
        """
        更新策略表现

        Args:
            name: 策略名称
            performance: 表现数据
        """
        if name not in self.strategies:
            logger.warning(f"策略不存在: {name}")
            return

        self.performance_history[name] = performance
        logger.debug(f"策略表现已更新: {name}, 收益率={performance.total_return:.2%}")

    def calculate_sharpe_ratio(self, returns: List[float]) -> float:
        """计算夏普比率"""
        if len(returns) < 2:
            return 0.0

        returns_array = np.array(returns)
        mean_return = np.mean(returns_array)
        std_return = np.std(returns_array)

        if std_return == 0:
            return 0.0

        sharpe = (mean_return / std_return) * np.sqrt(252)
        return sharpe

    def calculate_sortino_ratio(self, returns: List[float]) -> float:
        """计算Sortino比率"""
        if len(returns) < 2:
            return 0.0

        returns_array = np.array(returns)
        mean_return = np.mean(returns_array)

        negative_returns = returns_array[returns_array < 0]
        if len(negative_returns) == 0:
            return mean_return * np.sqrt(252) * 100  # 很高的值

        downside_std = np.std(negative_returns)
        if downside_std == 0:
            return 0.0

        sortino = (mean_return / downside_std) * np.sqrt(252)
        return sortino

    def calculate_correlation_matrix(self) -> pd.DataFrame:
        """
        计算策略收益率相关性矩阵

        Returns:
            相关性矩阵DataFrame
        """
        # 收集所有策略的收益率
        returns_dict = {}
        for name, perf in self.performance_history.items():
            if len(perf.returns) > 0:
                returns_dict[name] = perf.returns

        if not returns_dict:
            return pd.DataFrame()

        # 确保所有收益率序列长度一致
        min_length = min(len(r) for r in returns_dict.values())
        aligned_returns = {name: rets[-min_length:] for name, rets in returns_dict.items()}

        # 创建DataFrame并计算相关性
        df = pd.DataFrame(aligned_returns)
        corr_matrix = df.corr()

        logger.info(f"相关性矩阵已计算, 维度: {corr_matrix.shape}")
        return corr_matrix

    def optimize_allocation_sharpe(self) -> Dict[str, float]:
        """
        基于最大夏普比率优化分配

        Returns:
            优化后的分配字典
        """
        active_strategies = {name: perf for name, perf in self.performance_history.items()
                           if self.strategies[name].enabled and len(perf.returns) > 10}

        if len(active_strategies) < 2:
            logger.warning("活跃策略数量不足，无法优化")
            return self.allocations

        # 准备数据
        strategy_names = list(active_strategies.keys())
        returns_data = []

        # 确保所有收益率序列长度一致
        min_length = min(len(perf.returns) for perf in active_strategies.values())
        for name in strategy_names:
            returns_data.append(active_strategies[name].returns[-min_length:])

        returns_matrix = np.array(returns_data).T  # 转置：行为时间点，列为策略

        # 计算均值和协方差矩阵
        mean_returns = np.mean(returns_matrix, axis=0)
        cov_matrix = np.cov(returns_matrix.T)

        # 定义优化目标：最大化夏普比率
        def negative_sharpe(weights):
            portfolio_return = np.dot(weights, mean_returns)
            portfolio_std = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights)))
            if portfolio_std == 0:
                return 1e10
            sharpe = portfolio_return / portfolio_std
            return -sharpe  # 最小化负夏普

        # 约束条件
        constraints = [
            {'type': 'eq', 'fun': lambda w: np.sum(w) - 1}  # 权重和为1
        ]

        # 边界条件
        bounds = []
        for name in strategy_names:
            config = self.strategies[name]
            bounds.append((config.min_allocation, config.max_allocation))

        # 初始猜测（等权重）
        n_strategies = len(strategy_names)
        initial_weights = np.array([1.0 / n_strategies] * n_strategies)

        # 优化
        result = minimize(
            negative_sharpe,
            initial_weights,
            method='SLSQP',
            bounds=bounds,
            constraints=constraints
        )

        if result.success:
            # 转换为资金分配
            optimal_allocations = {}
            for i, name in enumerate(strategy_names):
                optimal_allocations[name] = result.x[i] * self.total_capital

            logger.info(f"分配优化完成, 夏普比率: {-result.fun:.3f}")
            return optimal_allocations
        else:
            logger.warning("分配优化失败，保持当前分配")
            return self.allocations

    def optimize_allocation_risk_parity(self) -> Dict[str, float]:
        """
        风险平价分配

        Returns:
            风险平价分配字典
        """
        active_strategies = {name: perf for name, perf in self.performance_history.items()
                           if self.strategies[name].enabled and len(perf.returns) > 10}

        if len(active_strategies) < 2:
            return self.allocations

        # 计算每个策略的波动率
        strategy_names = list(active_strategies.keys())
        volatilities = []

        for name in strategy_names:
            returns = np.array(active_strategies[name].returns)
            vol = np.std(returns)
            volatilities.append(vol if vol > 0 else 0.0001)

        # 风险平价：权重与波动率成反比
        inverse_vols = 1.0 / np.array(volatilities)
        weights = inverse_vols / np.sum(inverse_vols)

        # 应用最小最大限制
        for i, name in enumerate(strategy_names):
            config = self.strategies[name]
            weights[i] = np.clip(weights[i], config.min_allocation, config.max_allocation)

        # 重新归一化
        weights = weights / np.sum(weights)

        # 转换为资金分配
        allocations = {}
        for i, name in enumerate(strategy_names):
            allocations[name] = weights[i] * self.total_capital

        logger.info("风险平价分配已计算")
        return allocations

    def rebalance(self, method: str = 'sharpe'):
        """
        再平衡策略分配

        Args:
            method: 'sharpe' - 最大化夏普比率
                   'risk_parity' - 风险平价
                   'equal' - 等权重
                   'performance' - 基于表现
        """
        logger.info(f"开始再平衡，方法: {method}")

        if method == 'sharpe':
            new_allocations = self.optimize_allocation_sharpe()
        elif method == 'risk_parity':
            new_allocations = self.optimize_allocation_risk_parity()
        elif method == 'equal':
            active_strategies = [name for name, config in self.strategies.items()
                               if config.enabled]
            weight = 1.0 / len(active_strategies) if active_strategies else 0
            new_allocations = {name: weight * self.total_capital
                             for name in active_strategies}
        elif method == 'performance':
            new_allocations = self._performance_based_allocation()
        else:
            logger.warning(f"未知的再平衡方法: {method}")
            return

        # 更新分配
        old_allocations = self.allocations.copy()
        self.allocations = new_allocations

        # 记录变化
        logger.info("再平衡完成:")
        for name in self.allocations:
            old_amt = old_allocations.get(name, 0)
            new_amt = new_allocations.get(name, 0)
            change = new_amt - old_amt
            logger.info(f"  {name}: ${old_amt:.2f} -> ${new_amt:.2f} "
                       f"(变化: ${change:+.2f})")

    def _performance_based_allocation(self) -> Dict[str, float]:
        """基于表现的分配"""
        active_strategies = {name: perf for name, perf in self.performance_history.items()
                           if self.strategies[name].enabled and perf.total_trades > 0}

        if not active_strategies:
            return self.allocations

        # 计算综合得分（夏普比率 + 收益率）
        scores = {}
        for name, perf in active_strategies.items():
            # 得分 = 标准化夏普 + 标准化收益率
            score = max(0, perf.sharpe_ratio) + max(0, perf.total_return)
            scores[name] = score

        total_score = sum(scores.values())
        if total_score == 0:
            # 等权重
            weight = 1.0 / len(active_strategies)
            return {name: weight * self.total_capital for name in active_strategies}

        # 按得分分配
        allocations = {}
        for name, score in scores.items():
            weight = score / total_score
            # 应用限制
            config = self.strategies[name]
            weight = np.clip(weight, config.min_allocation, config.max_allocation)
            allocations[name] = weight * self.total_capital

        # 归一化
        total_allocated = sum(allocations.values())
        if total_allocated > 0:
            for name in allocations:
                allocations[name] = (allocations[name] / total_allocated) * self.total_capital

        return allocations

    def get_portfolio_metrics(self) -> Dict:
        """
        获取组合指标

        Returns:
            组合指标字典
        """
        # 汇总所有策略的收益
        total_capital = sum(perf.current_capital
                          for perf in self.performance_history.values())

        # 计算组合收益率
        portfolio_return = (total_capital - self.total_capital) / self.total_capital

        # 计算组合权益曲线（加权平均）
        max_length = max((len(perf.equity_curve)
                        for perf in self.performance_history.values()), default=0)

        portfolio_equity = []
        for i in range(max_length):
            equity_sum = 0
            for name, perf in self.performance_history.items():
                if i < len(perf.equity_curve):
                    weight = self.allocations.get(name, 0) / self.total_capital
                    equity_sum += perf.equity_curve[i] * weight
            portfolio_equity.append(equity_sum)

        # 计算组合收益率序列
        portfolio_returns = []
        for i in range(1, len(portfolio_equity)):
            ret = (portfolio_equity[i] - portfolio_equity[i-1]) / portfolio_equity[i-1]
            portfolio_returns.append(ret)

        # 计算组合夏普比率
        portfolio_sharpe = self.calculate_sharpe_ratio(portfolio_returns)

        # 计算组合最大回撤
        if portfolio_equity:
            equity_array = np.array(portfolio_equity)
            running_max = np.maximum.accumulate(equity_array)
            drawdown = (equity_array - running_max) / running_max
            max_drawdown = abs(drawdown.min()) if len(drawdown) > 0 else 0
        else:
            max_drawdown = 0

        return {
            'total_capital': total_capital,
            'portfolio_return': portfolio_return,
            'portfolio_sharpe': portfolio_sharpe,
            'max_drawdown': max_drawdown,
            'num_strategies': len(self.strategies),
            'active_strategies': sum(1 for c in self.strategies.values() if c.enabled)
        }

    def export_allocation_report(self, filename: str = 'portfolio_report.txt'):
        """导出组合报告"""
        portfolio_metrics = self.get_portfolio_metrics()
        corr_matrix = self.calculate_correlation_matrix()

        report = f"""
╔════════════════════════════════════════════════════════════╗
║                    策略组合报告                              ║
╚════════════════════════════════════════════════════════════╝

📊 组合概览
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  总资金:        ${self.total_capital:>12,.2f}
  当前权益:      ${portfolio_metrics['total_capital']:>12,.2f}
  组合收益率:     {portfolio_metrics['portfolio_return']:>12.2%}
  组合夏普:      {portfolio_metrics['portfolio_sharpe']:>12.3f}
  最大回撤:      {portfolio_metrics['max_drawdown']:>12.2%}
  策略数量:      {portfolio_metrics['num_strategies']:>12d}
  活跃策略:      {portfolio_metrics['active_strategies']:>12d}

💰 策略分配
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

        for name, allocation in sorted(self.allocations.items(),
                                       key=lambda x: x[1], reverse=True):
            perf = self.performance_history.get(name)
            config = self.strategies.get(name)
            status = "✅" if config.enabled else "⏸️"

            weight = allocation / self.total_capital
            report += f"  {status} {name:20s} ${allocation:>10,.2f} ({weight:>6.2%})"

            if perf and perf.total_trades > 0:
                report += f"  收益:{perf.total_return:>7.2%}  夏普:{perf.sharpe_ratio:>6.2f}\n"
            else:
                report += "  无交易数据\n"

        report += f"""
📈 策略表现详情
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

        for name, perf in self.performance_history.items():
            if perf.total_trades == 0:
                continue

            report += f"""
  {name}
  ──────────────────────────────────────────────────────
    总收益率:     {perf.total_return:>12.2%}
    夏普比率:     {perf.sharpe_ratio:>12.3f}
    Sortino比率:  {perf.sortino_ratio:>12.3f}
    最大回撤:     {perf.max_drawdown:>12.2%}
    胜率:         {perf.win_rate:>12.2%}
    盈亏比:       {perf.profit_factor:>12.3f}
    总交易:       {perf.total_trades:>12d}
    平均盈亏:     ${perf.avg_trade_pnl:>11,.2f}
"""

        if not corr_matrix.empty:
            report += f"""
🔗 策略相关性矩阵
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{corr_matrix.to_string()}
"""

        report += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
报告时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""

        with open(filename, 'w', encoding='utf-8') as f:
            f.write(report)

        logger.info(f"组合报告已导出: {filename}")
        return report


class PortfolioManager:
    """组合管理器（集成风险管理）"""

    def __init__(self, total_capital: float):
        """
        初始化组合管理器

        Args:
            total_capital: 总资金
        """
        self.allocator = StrategyAllocation(total_capital)
        self.rebalance_interval = timedelta(days=7)  # 再平衡间隔
        self.last_rebalance = datetime.now()

    def add_strategy(self, name: str, strategy_type: str,
                    initial_allocation: float = 0.25,
                    min_allocation: float = 0.05,
                    max_allocation: float = 0.50):
        """添加策略"""
        config = StrategyConfig(
            name=name,
            strategy_type=strategy_type,
            initial_allocation=initial_allocation,
            min_allocation=min_allocation,
            max_allocation=max_allocation
        )
        self.allocator.register_strategy(config)

    def update_strategy_results(self, name: str, equity_curve: List[float],
                               returns: List[float], trades_data: List[Dict]):
        """
        更新策略结果

        Args:
            name: 策略名称
            equity_curve: 权益曲线
            returns: 收益率序列
            trades_data: 交易数据
        """
        # 计算表现指标
        if not trades_data:
            return

        wins = [t['pnl'] for t in trades_data if t.get('pnl', 0) > 0]
        losses = [abs(t['pnl']) for t in trades_data if t.get('pnl', 0) < 0]

        total_return = (equity_curve[-1] - equity_curve[0]) / equity_curve[0] if equity_curve else 0
        win_rate = len(wins) / len(trades_data) if trades_data else 0
        profit_factor = sum(wins) / sum(losses) if losses else (float('inf') if wins else 0)
        avg_trade_pnl = np.mean([t.get('pnl', 0) for t in trades_data])

        # 计算最大回撤
        equity_array = np.array(equity_curve)
        running_max = np.maximum.accumulate(equity_array)
        drawdown = (equity_array - running_max) / running_max
        max_drawdown = abs(drawdown.min()) if len(drawdown) > 0 else 0

        # 创建表现对象
        performance = StrategyPerformance(
            name=name,
            total_return=total_return,
            sharpe_ratio=self.allocator.calculate_sharpe_ratio(returns),
            sortino_ratio=self.allocator.calculate_sortino_ratio(returns),
            max_drawdown=max_drawdown,
            win_rate=win_rate,
            profit_factor=profit_factor,
            total_trades=len(trades_data),
            avg_trade_pnl=avg_trade_pnl,
            current_capital=equity_curve[-1] if equity_curve else 0,
            equity_curve=equity_curve,
            returns=returns
        )

        self.allocator.update_strategy_performance(name, performance)

    def should_rebalance(self) -> bool:
        """是否应该再平衡"""
        return datetime.now() - self.last_rebalance >= self.rebalance_interval

    def rebalance_if_needed(self, method: str = 'sharpe'):
        """如果需要则再平衡"""
        if self.should_rebalance():
            self.allocator.rebalance(method)
            self.last_rebalance = datetime.now()
            logger.info("组合已再平衡")

    def get_strategy_allocation(self, name: str) -> float:
        """获取策略分配资金"""
        return self.allocator.allocations.get(name, 0)

    def export_report(self, filename: str = 'portfolio_report.txt'):
        """导出报告"""
        return self.allocator.export_allocation_report(filename)


def main():
    """测试示例"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("=" * 60)
    print("策略组合管理系统测试")
    print("=" * 60)

    # 创建组合管理器
    portfolio = PortfolioManager(total_capital=10000)

    # 添加策略
    print("\n1. 添加策略...")
    portfolio.add_strategy('ML策略', 'ml', initial_allocation=0.35)
    portfolio.add_strategy('订单簿策略', 'orderbook', initial_allocation=0.35)
    portfolio.add_strategy('趋势策略', 'trend', initial_allocation=0.30)

    # 模拟策略表现
    print("\n2. 模拟策略表现...")

    # ML策略表现
    ml_equity = [3500 + i * 10 + np.random.randn() * 5 for i in range(100)]
    ml_returns = [0.01 + np.random.randn() * 0.02 for _ in range(99)]
    ml_trades = [{'pnl': 10 + np.random.randn() * 5} for _ in range(30)]

    portfolio.update_strategy_results('ML策略', ml_equity, ml_returns, ml_trades)

    # 订单簿策略表现
    ob_equity = [3500 + i * 8 + np.random.randn() * 8 for i in range(100)]
    ob_returns = [0.008 + np.random.randn() * 0.025 for _ in range(99)]
    ob_trades = [{'pnl': 8 + np.random.randn() * 6} for _ in range(40)]

    portfolio.update_strategy_results('订单簿策略', ob_equity, ob_returns, ob_trades)

    # 趋势策略表现
    trend_equity = [3000 + i * 12 + np.random.randn() * 10 for i in range(100)]
    trend_returns = [0.012 + np.random.randn() * 0.03 for _ in range(99)]
    trend_trades = [{'pnl': 12 + np.random.randn() * 8} for _ in range(25)]

    portfolio.update_strategy_results('趋势策略', trend_equity, trend_returns, trend_trades)

    # 查看组合指标
    print("\n3. 组合指标...")
    metrics = portfolio.allocator.get_portfolio_metrics()
    for key, value in metrics.items():
        if isinstance(value, float):
            if 'return' in key or 'drawdown' in key:
                print(f"   {key}: {value:.2%}")
            else:
                print(f"   {key}: {value:.3f}")
        else:
            print(f"   {key}: {value}")

    # 相关性分析
    print("\n4. 策略相关性...")
    corr = portfolio.allocator.calculate_correlation_matrix()
    if not corr.empty:
        print(corr)

    # 优化分配
    print("\n5. 优化分配（最大化夏普）...")
    portfolio.allocator.rebalance('sharpe')

    print("\n6. 当前分配:")
    for name, amount in portfolio.allocator.allocations.items():
        weight = amount / portfolio.allocator.total_capital
        print(f"   {name}: ${amount:.2f} ({weight:.2%})")

    # 导出报告
    print("\n7. 导出报告...")
    report = portfolio.export_report()
    print(report)


if __name__ == '__main__':
    main()
