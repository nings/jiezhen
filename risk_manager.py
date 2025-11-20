#!/usr/bin/env python3
"""
动态风险管理系统

功能：
- Kelly准则仓位计算
- VaR（风险价值）计算
- 每日风险预算管理
- 风险警报和自动停止
- 回撤监控
- 暴露限制
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
from scipy import stats

logger = logging.getLogger(__name__)


@dataclass
class RiskLimits:
    """风险限制配置"""
    max_daily_loss: float = 500.0  # 最大日亏损
    max_drawdown_pct: float = 0.15  # 最大回撤百分比
    max_position_size: float = 1000.0  # 单笔最大仓位
    max_total_exposure: float = 5000.0  # 最大总暴露
    max_leverage: float = 10.0  # 最大杠杆
    var_limit: float = 300.0  # VaR限制
    concentration_limit: float = 0.3  # 单一品种最大占比


@dataclass
class RiskMetrics:
    """风险指标"""
    current_drawdown: float = 0.0
    daily_pnl: float = 0.0
    total_exposure: float = 0.0
    var_95: float = 0.0
    var_99: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    max_consecutive_losses: int = 0
    current_consecutive_losses: int = 0


class RiskManager:
    """风险管理器"""

    def __init__(self, initial_capital: float, limits: RiskLimits = None):
        """
        初始化风险管理器

        Args:
            initial_capital: 初始资金
            limits: 风险限制配置
        """
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.limits = limits or RiskLimits()

        # 历史数据
        self.equity_history = [initial_capital]
        self.returns_history = []
        self.trades_history = []
        self.daily_pnl_history = []

        # 当前状态
        self.positions = {}  # inst_id -> position_info
        self.daily_pnl = 0.0
        self.peak_equity = initial_capital
        self.is_trading_allowed = True
        self.risk_alerts = []

        # 统计
        self.consecutive_losses = 0
        self.max_consecutive_losses = 0

    def kelly_position_size(self, win_rate: float, avg_win: float, avg_loss: float,
                           max_kelly_fraction: float = 0.25) -> float:
        """
        Kelly准则计算最优仓位

        Args:
            win_rate: 胜率
            avg_win: 平均盈利
            avg_loss: 平均亏损（正数）
            max_kelly_fraction: 最大Kelly比例（保守起见）

        Returns:
            建议仓位比例
        """
        if win_rate <= 0 or win_rate >= 1:
            return 0.0

        if avg_loss <= 0:
            return 0.0

        # Kelly公式: f = (p * b - q) / b
        # 其中 p=胜率, q=1-p, b=avg_win/avg_loss
        b = avg_win / avg_loss
        q = 1 - win_rate
        kelly = (win_rate * b - q) / b

        # 限制最大Kelly比例（通常使用25%-50%的Kelly值）
        kelly = max(0, min(kelly, max_kelly_fraction))

        logger.info(f"Kelly仓位计算: 胜率={win_rate:.2%}, 盈亏比={b:.2f}, Kelly={kelly:.2%}")
        return kelly

    def calculate_position_size(self, signal_strength: float = 1.0,
                                volatility: float = 0.02) -> float:
        """
        计算建议仓位大小

        Args:
            signal_strength: 信号强度 (0-1)
            volatility: 预期波动率

        Returns:
            建议仓位金额
        """
        # 基于历史交易计算Kelly比例
        if len(self.trades_history) >= 10:
            wins = [t['pnl'] for t in self.trades_history if t['pnl'] > 0]
            losses = [abs(t['pnl']) for t in self.trades_history if t['pnl'] < 0]

            if wins and losses:
                win_rate = len(wins) / len(self.trades_history)
                avg_win = np.mean(wins)
                avg_loss = np.mean(losses)
                kelly_fraction = self.kelly_position_size(win_rate, avg_win, avg_loss)
            else:
                kelly_fraction = 0.1  # 默认10%
        else:
            kelly_fraction = 0.1

        # 根据波动率调整
        volatility_adjustment = 1 / (1 + volatility * 10)

        # 计算基础仓位
        base_position = self.current_capital * kelly_fraction * signal_strength * volatility_adjustment

        # 应用限制
        position_size = min(base_position, self.limits.max_position_size)

        # 检查总暴露限制
        current_exposure = sum(abs(pos['size'] * pos['price'])
                              for pos in self.positions.values())
        remaining_exposure = self.limits.max_total_exposure - current_exposure

        position_size = min(position_size, remaining_exposure)

        logger.info(f"仓位计算: Kelly={kelly_fraction:.2%}, 信号={signal_strength:.2f}, "
                   f"波动率={volatility:.2%}, 建议仓位=${position_size:.2f}")

        return max(0, position_size)

    def calculate_var(self, confidence_level: float = 0.95,
                     horizon_days: int = 1) -> float:
        """
        计算VaR（风险价值）

        Args:
            confidence_level: 置信水平
            horizon_days: 时间范围（天）

        Returns:
            VaR值
        """
        if len(self.returns_history) < 30:
            # 历史数据不足，使用保守估计
            return self.current_capital * 0.02 * np.sqrt(horizon_days)

        returns = np.array(self.returns_history)

        # 方法1: 历史模拟法
        var_historical = np.percentile(returns, (1 - confidence_level) * 100)

        # 方法2: 参数法（假设正态分布）
        mean_return = np.mean(returns)
        std_return = np.std(returns)
        z_score = stats.norm.ppf(1 - confidence_level)
        var_parametric = mean_return + z_score * std_return

        # 使用两种方法的最大值（保守）
        var_return = min(var_historical, var_parametric)

        # 转换为金额
        var_amount = abs(var_return * self.current_capital * np.sqrt(horizon_days))

        logger.info(f"VaR计算: {confidence_level:.0%}置信度, {horizon_days}天, "
                   f"VaR=${var_amount:.2f}")

        return var_amount

    def calculate_cvar(self, confidence_level: float = 0.95) -> float:
        """
        计算CVaR（条件风险价值，预期亏空）

        Args:
            confidence_level: 置信水平

        Returns:
            CVaR值
        """
        if len(self.returns_history) < 30:
            return self.current_capital * 0.03

        returns = np.array(self.returns_history)
        var_threshold = np.percentile(returns, (1 - confidence_level) * 100)

        # CVaR是超过VaR的平均损失
        tail_losses = returns[returns <= var_threshold]
        cvar_return = np.mean(tail_losses) if len(tail_losses) > 0 else var_threshold

        cvar_amount = abs(cvar_return * self.current_capital)

        logger.info(f"CVaR计算: {confidence_level:.0%}置信度, CVaR=${cvar_amount:.2f}")
        return cvar_amount

    def check_risk_limits(self) -> Tuple[bool, List[str]]:
        """
        检查风险限制

        Returns:
            (是否允许交易, 警告列表)
        """
        warnings = []

        # 检查日亏损限制
        if self.daily_pnl < -self.limits.max_daily_loss:
            warnings.append(f"🔴 触发日亏损限制: ${self.daily_pnl:.2f} < -${self.limits.max_daily_loss}")
            self.is_trading_allowed = False

        # 检查最大回撤
        current_drawdown = (self.peak_equity - self.current_capital) / self.peak_equity
        if current_drawdown > self.limits.max_drawdown_pct:
            warnings.append(f"🔴 触发最大回撤限制: {current_drawdown:.2%} > {self.limits.max_drawdown_pct:.2%}")
            self.is_trading_allowed = False

        # 检查VaR限制
        var_95 = self.calculate_var(0.95)
        if var_95 > self.limits.var_limit:
            warnings.append(f"🟠 VaR超限: ${var_95:.2f} > ${self.limits.var_limit}")

        # 检查总暴露
        total_exposure = sum(abs(pos['size'] * pos['price'])
                           for pos in self.positions.values())
        if total_exposure > self.limits.max_total_exposure:
            warnings.append(f"🟠 总暴露超限: ${total_exposure:.2f} > ${self.limits.max_total_exposure}")

        # 检查集中度
        if self.positions:
            for inst_id, pos in self.positions.items():
                exposure = abs(pos['size'] * pos['price'])
                concentration = exposure / self.current_capital
                if concentration > self.limits.concentration_limit:
                    warnings.append(f"🟡 {inst_id}集中度过高: {concentration:.2%}")

        # 连续亏损警告
        if self.consecutive_losses >= 5:
            warnings.append(f"🟡 连续亏损{self.consecutive_losses}次，建议暂停交易")

        self.risk_alerts = warnings
        return self.is_trading_allowed, warnings

    def update_position(self, inst_id: str, size: float, price: float,
                       side: str = 'long'):
        """
        更新持仓

        Args:
            inst_id: 交易对
            size: 数量
            price: 价格
            side: 方向
        """
        self.positions[inst_id] = {
            'size': size if side == 'long' else -size,
            'price': price,
            'side': side,
            'timestamp': datetime.now()
        }

    def close_position(self, inst_id: str, exit_price: float, pnl: float):
        """
        平仓

        Args:
            inst_id: 交易对
            exit_price: 平仓价格
            pnl: 盈亏
        """
        if inst_id in self.positions:
            # 记录交易
            trade = {
                'inst_id': inst_id,
                'pnl': pnl,
                'timestamp': datetime.now()
            }
            self.trades_history.append(trade)

            # 更新资金
            self.current_capital += pnl
            self.daily_pnl += pnl
            self.equity_history.append(self.current_capital)

            # 更新峰值
            if self.current_capital > self.peak_equity:
                self.peak_equity = self.current_capital

            # 计算收益率
            if len(self.equity_history) > 1:
                ret = (self.equity_history[-1] - self.equity_history[-2]) / self.equity_history[-2]
                self.returns_history.append(ret)

            # 更新连续亏损计数
            if pnl < 0:
                self.consecutive_losses += 1
                self.max_consecutive_losses = max(self.max_consecutive_losses,
                                                 self.consecutive_losses)
            else:
                self.consecutive_losses = 0

            # 移除持仓
            del self.positions[inst_id]

            logger.info(f"平仓: {inst_id}, PnL=${pnl:.2f}, 权益=${self.current_capital:.2f}")

    def reset_daily_pnl(self):
        """重置每日盈亏（每天开始时调用）"""
        self.daily_pnl_history.append(self.daily_pnl)
        self.daily_pnl = 0.0
        logger.info("每日盈亏已重置")

    def get_risk_metrics(self) -> RiskMetrics:
        """
        获取风险指标

        Returns:
            风险指标对象
        """
        # 计算当前回撤
        current_drawdown = (self.peak_equity - self.current_capital) / self.peak_equity

        # 计算夏普比率
        if len(self.returns_history) > 1:
            returns = np.array(self.returns_history)
            sharpe = (np.mean(returns) / np.std(returns)) * np.sqrt(252) if np.std(returns) > 0 else 0
        else:
            sharpe = 0

        # 计算Sortino比率（只考虑下行波动）
        if len(self.returns_history) > 1:
            returns = np.array(self.returns_history)
            negative_returns = returns[returns < 0]
            downside_std = np.std(negative_returns) if len(negative_returns) > 0 else 0.0001
            sortino = (np.mean(returns) / downside_std) * np.sqrt(252) if downside_std > 0 else 0
        else:
            sortino = 0

        # 计算总暴露
        total_exposure = sum(abs(pos['size'] * pos['price'])
                           for pos in self.positions.values())

        return RiskMetrics(
            current_drawdown=current_drawdown,
            daily_pnl=self.daily_pnl,
            total_exposure=total_exposure,
            var_95=self.calculate_var(0.95),
            var_99=self.calculate_var(0.99),
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            max_consecutive_losses=self.max_consecutive_losses,
            current_consecutive_losses=self.consecutive_losses
        )

    def suggest_stop_loss(self, entry_price: float, side: str,
                         atr: float = None) -> float:
        """
        建议止损价格

        Args:
            entry_price: 入场价格
            side: 方向
            atr: ATR（平均真实波动幅度）

        Returns:
            止损价格
        """
        # 方法1: 基于ATR
        if atr is not None:
            stop_distance = 2 * atr  # 2倍ATR
        else:
            # 方法2: 基于百分比
            stop_distance = entry_price * 0.02  # 2%

        if side == 'long':
            stop_price = entry_price - stop_distance
        else:
            stop_price = entry_price + stop_distance

        logger.info(f"建议止损: 入场={entry_price}, 方向={side}, 止损={stop_price:.2f}")
        return stop_price

    def suggest_take_profit(self, entry_price: float, side: str,
                           risk_reward_ratio: float = 2.0,
                           atr: float = None) -> float:
        """
        建议止盈价格

        Args:
            entry_price: 入场价格
            side: 方向
            risk_reward_ratio: 风险收益比
            atr: ATR

        Returns:
            止盈价格
        """
        # 计算止损距离
        if atr is not None:
            stop_distance = 2 * atr
        else:
            stop_distance = entry_price * 0.02

        # 止盈距离 = 止损距离 × 风险收益比
        profit_distance = stop_distance * risk_reward_ratio

        if side == 'long':
            take_profit = entry_price + profit_distance
        else:
            take_profit = entry_price - profit_distance

        logger.info(f"建议止盈: 入场={entry_price}, 方向={side}, "
                   f"风险收益比={risk_reward_ratio}, 止盈={take_profit:.2f}")
        return take_profit

    def export_risk_report(self, filename: str = 'risk_report.txt'):
        """导出风险报告"""
        metrics = self.get_risk_metrics()
        is_allowed, warnings = self.check_risk_limits()

        report = f"""
╔════════════════════════════════════════════════════════════╗
║                     风险管理报告                             ║
╚════════════════════════════════════════════════════════════╝

📊 资金状况
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  初始资金:      ${self.initial_capital:>12,.2f}
  当前权益:      ${self.current_capital:>12,.2f}
  峰值权益:      ${self.peak_equity:>12,.2f}
  今日盈亏:      ${metrics.daily_pnl:>12,.2f}

📉 风险指标
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  当前回撤:      {metrics.current_drawdown:>12.2%}
  VaR (95%):     ${metrics.var_95:>12,.2f}
  VaR (99%):     ${metrics.var_99:>12,.2f}
  总暴露:        ${metrics.total_exposure:>12,.2f}

📈 绩效指标
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  夏普比率:      {metrics.sharpe_ratio:>12.3f}
  Sortino比率:   {metrics.sortino_ratio:>12.3f}
  最大连续亏损:   {metrics.max_consecutive_losses:>12d}
  当前连续亏损:   {metrics.current_consecutive_losses:>12d}

🎯 持仓状况
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  持仓数量:      {len(self.positions):>12d}
"""

        if self.positions:
            for inst_id, pos in self.positions.items():
                exposure = abs(pos['size'] * pos['price'])
                concentration = exposure / self.current_capital
                report += f"  {inst_id:20s} {pos['side']:>5s} ${exposure:>10,.2f} ({concentration:>6.2%})\n"

        report += f"""
⚠️  风险警报
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  交易状态:      {'✅ 允许' if is_allowed else '🛑 禁止'}
  警报数量:      {len(warnings)}
"""

        if warnings:
            for warning in warnings:
                report += f"  {warning}\n"
        else:
            report += "  ✅ 所有风险指标正常\n"

        report += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
报告时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""

        with open(filename, 'w', encoding='utf-8') as f:
            f.write(report)

        logger.info(f"风险报告已导出: {filename}")
        return report


def main():
    """测试示例"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # 创建风险管理器
    risk_manager = RiskManager(initial_capital=10000)

    print("=" * 60)
    print("风险管理系统测试")
    print("=" * 60)

    # 模拟一些交易
    print("\n1. 计算建议仓位...")
    position_size = risk_manager.calculate_position_size(
        signal_strength=0.8,
        volatility=0.015
    )
    print(f"   建议仓位: ${position_size:.2f}")

    # 开仓
    print("\n2. 开仓测试...")
    risk_manager.update_position('BTC-USDT-SWAP', 0.1, 50000, 'long')

    # 计算止损止盈
    stop_loss = risk_manager.suggest_stop_loss(50000, 'long', atr=500)
    take_profit = risk_manager.suggest_take_profit(50000, 'long', risk_reward_ratio=2.5)
    print(f"   止损价格: ${stop_loss:.2f}")
    print(f"   止盈价格: ${take_profit:.2f}")

    # 模拟几笔交易
    print("\n3. 模拟交易历史...")
    trades = [
        (100, 'win'),
        (-50, 'loss'),
        (150, 'win'),
        (80, 'win'),
        (-40, 'loss'),
        (120, 'win'),
        (-60, 'loss'),
        (90, 'win')
    ]

    for pnl, result in trades:
        risk_manager.close_position('BTC-USDT-SWAP', 50000 + pnl * 10, pnl)
        risk_manager.update_position('BTC-USDT-SWAP', 0.1, 50000, 'long')

    # 获取风险指标
    print("\n4. 风险指标...")
    metrics = risk_manager.get_risk_metrics()
    print(f"   当前回撤: {metrics.current_drawdown:.2%}")
    print(f"   VaR (95%): ${metrics.var_95:.2f}")
    print(f"   夏普比率: {metrics.sharpe_ratio:.3f}")
    print(f"   Sortino比率: {metrics.sortino_ratio:.3f}")

    # 检查风险限制
    print("\n5. 风险限制检查...")
    is_allowed, warnings = risk_manager.check_risk_limits()
    print(f"   交易状态: {'✅ 允许' if is_allowed else '🛑 禁止'}")
    if warnings:
        print("   警告:")
        for warning in warnings:
            print(f"     {warning}")

    # 导出报告
    print("\n6. 导出风险报告...")
    report = risk_manager.export_risk_report()
    print(report)


if __name__ == '__main__':
    main()
