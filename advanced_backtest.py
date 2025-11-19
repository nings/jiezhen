#!/usr/bin/env python3
"""
高级回测引擎

功能特性：
- 精确的滑点模拟
- 手续费计算（maker/taker）
- 全面的风险指标
- 交易统计分析
- 性能报告生成
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
from datetime import datetime
import json


@dataclass
class BacktestConfig:
    """回测配置"""
    initial_capital: float = 10000.0  # 初始资金
    position_size: float = 100.0  # 单笔交易金额
    leverage: float = 10.0  # 杠杆倍数
    maker_fee: float = 0.0002  # Maker手续费 0.02%
    taker_fee: float = 0.0005  # Taker手续费 0.05%
    slippage: float = 0.0001  # 滑点 0.01%
    stop_loss_pct: float = 0.02  # 止损百分比 2%
    take_profit_pct: float = 0.03  # 止盈百分比 3%
    max_positions: int = 3  # 最大同时持仓数
    risk_free_rate: float = 0.03  # 无风险利率（年化）


@dataclass
class Trade:
    """交易记录"""
    timestamp: int
    symbol: str
    side: str  # 'long' or 'short'
    entry_price: float
    exit_price: Optional[float] = None
    size: float = 0.0
    entry_fee: float = 0.0
    exit_fee: float = 0.0
    pnl: float = 0.0
    pnl_pct: float = 0.0
    exit_reason: Optional[str] = None  # 'take_profit', 'stop_loss', 'signal', 'timeout'
    hold_time: int = 0  # 持仓时间（秒）


@dataclass
class BacktestResult:
    """回测结果"""
    # 基础指标
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0

    # 盈亏指标
    total_pnl: float = 0.0
    total_return: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 0.0

    # 风险指标
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_duration: int = 0
    calmar_ratio: float = 0.0

    # 其他指标
    avg_hold_time: float = 0.0
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0

    # 详细数据
    trades: List[Trade] = field(default_factory=list)
    equity_curve: List[float] = field(default_factory=list)
    daily_returns: List[float] = field(default_factory=list)


class AdvancedBacktester:
    """高级回测引擎"""

    def __init__(self, config: BacktestConfig = None):
        self.config = config or BacktestConfig()
        self.capital = self.config.initial_capital
        self.positions: List[Trade] = []
        self.closed_trades: List[Trade] = []
        self.equity_curve = [self.config.initial_capital]
        self.timestamps = []

    def calculate_fee(self, price: float, size: float, is_maker: bool = True) -> float:
        """计算手续费"""
        fee_rate = self.config.maker_fee if is_maker else self.config.taker_fee
        return price * size * fee_rate

    def apply_slippage(self, price: float, side: str) -> float:
        """应用滑点"""
        slippage = price * self.config.slippage
        if side == 'long':
            return price + slippage  # 买入时价格更高
        else:
            return price - slippage  # 卖出时价格更低

    def open_position(self, timestamp: int, symbol: str, signal: str, price: float,
                     is_maker: bool = True) -> Optional[Trade]:
        """开仓"""
        # 检查最大持仓数
        if len(self.positions) >= self.config.max_positions:
            return None

        # 应用滑点
        entry_price = self.apply_slippage(price, signal)

        # 计算仓位大小
        position_value = self.config.position_size * self.config.leverage
        size = position_value / entry_price

        # 计算手续费
        entry_fee = self.calculate_fee(entry_price, size, is_maker)

        # 检查是否有足够资金
        required_margin = position_value / self.config.leverage + entry_fee
        if required_margin > self.capital:
            return None

        # 创建交易
        trade = Trade(
            timestamp=timestamp,
            symbol=symbol,
            side=signal,
            entry_price=entry_price,
            size=size,
            entry_fee=entry_fee
        )

        self.positions.append(trade)
        self.capital -= (position_value / self.config.leverage + entry_fee)

        return trade

    def close_position(self, trade: Trade, timestamp: int, price: float,
                      reason: str, is_maker: bool = False) -> Trade:
        """平仓"""
        # 应用滑点
        exit_price = self.apply_slippage(price, 'short' if trade.side == 'long' else 'long')

        # 计算手续费
        exit_fee = self.calculate_fee(exit_price, trade.size, is_maker)

        # 计算盈亏
        if trade.side == 'long':
            pnl = (exit_price - trade.entry_price) * trade.size - trade.entry_fee - exit_fee
        else:  # short
            pnl = (trade.entry_price - exit_price) * trade.size - trade.entry_fee - exit_fee

        pnl_pct = (pnl / (trade.entry_price * trade.size)) * 100

        # 更新交易记录
        trade.exit_price = exit_price
        trade.exit_fee = exit_fee
        trade.pnl = pnl
        trade.pnl_pct = pnl_pct
        trade.exit_reason = reason
        trade.hold_time = timestamp - trade.timestamp

        # 更新资金
        position_value = trade.entry_price * trade.size
        self.capital += position_value / self.config.leverage + pnl

        # 移除持仓
        self.positions.remove(trade)
        self.closed_trades.append(trade)

        return trade

    def check_stop_loss_take_profit(self, timestamp: int, current_price: float):
        """检查止损止盈"""
        for trade in self.positions[:]:  # 使用切片避免迭代时修改
            if trade.side == 'long':
                # 多头止损止盈
                price_change_pct = (current_price - trade.entry_price) / trade.entry_price

                if price_change_pct <= -self.config.stop_loss_pct:
                    self.close_position(trade, timestamp, current_price, 'stop_loss', is_maker=False)
                elif price_change_pct >= self.config.take_profit_pct:
                    self.close_position(trade, timestamp, current_price, 'take_profit', is_maker=False)

            else:  # short
                # 空头止损止盈
                price_change_pct = (trade.entry_price - current_price) / trade.entry_price

                if price_change_pct <= -self.config.stop_loss_pct:
                    self.close_position(trade, timestamp, current_price, 'stop_loss', is_maker=False)
                elif price_change_pct >= self.config.take_profit_pct:
                    self.close_position(trade, timestamp, current_price, 'take_profit', is_maker=False)

    def process_signal(self, timestamp: int, symbol: str, signal: str,
                      price: float, confidence: float = 1.0):
        """处理交易信号"""
        # 记录权益
        self.timestamps.append(timestamp)

        # 检查止损止盈
        self.check_stop_loss_take_profit(timestamp, price)

        # 处理信号
        if signal == 'long':
            # 先平掉所有空头
            for trade in self.positions[:]:
                if trade.side == 'short':
                    self.close_position(trade, timestamp, price, 'signal', is_maker=True)

            # 开多头
            self.open_position(timestamp, symbol, 'long', price, is_maker=True)

        elif signal == 'short':
            # 先平掉所有多头
            for trade in self.positions[:]:
                if trade.side == 'long':
                    self.close_position(trade, timestamp, price, 'signal', is_maker=True)

            # 开空头
            self.open_position(timestamp, symbol, 'short', price, is_maker=True)

        elif signal == 'close_all':
            # 平掉所有持仓
            for trade in self.positions[:]:
                self.close_position(trade, timestamp, price, 'signal', is_maker=True)

        # 计算当前权益
        total_equity = self.capital
        for trade in self.positions:
            if trade.side == 'long':
                unrealized_pnl = (price - trade.entry_price) * trade.size
            else:
                unrealized_pnl = (trade.entry_price - price) * trade.size
            total_equity += unrealized_pnl

        self.equity_curve.append(total_equity)

    def calculate_metrics(self) -> BacktestResult:
        """计算回测指标"""
        result = BacktestResult()

        if not self.closed_trades:
            return result

        # 基础统计
        result.trades = self.closed_trades
        result.total_trades = len(self.closed_trades)
        result.winning_trades = sum(1 for t in self.closed_trades if t.pnl > 0)
        result.losing_trades = sum(1 for t in self.closed_trades if t.pnl < 0)
        result.win_rate = result.winning_trades / result.total_trades if result.total_trades > 0 else 0

        # 盈亏统计
        result.total_pnl = sum(t.pnl for t in self.closed_trades)
        result.total_return = (result.total_pnl / self.config.initial_capital) * 100

        winning_trades = [t.pnl for t in self.closed_trades if t.pnl > 0]
        losing_trades = [t.pnl for t in self.closed_trades if t.pnl < 0]

        result.avg_win = np.mean(winning_trades) if winning_trades else 0
        result.avg_loss = np.mean(losing_trades) if losing_trades else 0

        total_wins = sum(winning_trades)
        total_losses = abs(sum(losing_trades))
        result.profit_factor = total_wins / total_losses if total_losses > 0 else float('inf')

        # 权益曲线和收益率
        result.equity_curve = self.equity_curve
        returns = np.diff(self.equity_curve) / self.equity_curve[:-1]
        result.daily_returns = returns.tolist()

        # 夏普比率
        if len(returns) > 1:
            excess_returns = returns - (self.config.risk_free_rate / 252)  # 假设日收益
            result.sharpe_ratio = np.mean(excess_returns) / np.std(returns) * np.sqrt(252) if np.std(returns) > 0 else 0

        # 索提诺比率（只考虑下行波动）
        downside_returns = returns[returns < 0]
        if len(downside_returns) > 1:
            downside_std = np.std(downside_returns)
            result.sortino_ratio = np.mean(returns) / downside_std * np.sqrt(252) if downside_std > 0 else 0

        # 最大回撤
        equity_curve = np.array(self.equity_curve)
        running_max = np.maximum.accumulate(equity_curve)
        drawdown = (equity_curve - running_max) / running_max
        result.max_drawdown = abs(drawdown.min()) * 100

        # 最大回撤持续时间
        drawdown_duration = 0
        max_duration = 0
        for dd in drawdown:
            if dd < 0:
                drawdown_duration += 1
                max_duration = max(max_duration, drawdown_duration)
            else:
                drawdown_duration = 0
        result.max_drawdown_duration = max_duration

        # 卡尔玛比率
        annual_return = result.total_return / 100
        result.calmar_ratio = annual_return / (result.max_drawdown / 100) if result.max_drawdown > 0 else 0

        # 持仓时间
        hold_times = [t.hold_time for t in self.closed_trades]
        result.avg_hold_time = np.mean(hold_times) if hold_times else 0

        # 连续盈亏
        consecutive_wins = 0
        consecutive_losses = 0
        max_wins = 0
        max_losses = 0

        for trade in self.closed_trades:
            if trade.pnl > 0:
                consecutive_wins += 1
                consecutive_losses = 0
                max_wins = max(max_wins, consecutive_wins)
            else:
                consecutive_losses += 1
                consecutive_wins = 0
                max_losses = max(max_losses, consecutive_losses)

        result.max_consecutive_wins = max_wins
        result.max_consecutive_losses = max_losses

        return result

    def generate_report(self, result: BacktestResult) -> str:
        """生成回测报告"""
        report = []
        report.append("=" * 80)
        report.append("回测报告")
        report.append("=" * 80)

        report.append("\n【基础统计】")
        report.append(f"总交易次数: {result.total_trades}")
        report.append(f"盈利次数: {result.winning_trades}")
        report.append(f"亏损次数: {result.losing_trades}")
        report.append(f"胜率: {result.win_rate:.2%}")

        report.append("\n【盈亏指标】")
        report.append(f"总盈亏: ${result.total_pnl:.2f}")
        report.append(f"总收益率: {result.total_return:.2f}%")
        report.append(f"平均盈利: ${result.avg_win:.2f}")
        report.append(f"平均亏损: ${result.avg_loss:.2f}")
        report.append(f"盈亏比: {abs(result.avg_win / result.avg_loss) if result.avg_loss != 0 else 0:.2f}")
        report.append(f"盈利因子: {result.profit_factor:.2f}")

        report.append("\n【风险指标】")
        report.append(f"夏普比率: {result.sharpe_ratio:.3f}")
        report.append(f"索提诺比率: {result.sortino_ratio:.3f}")
        report.append(f"最大回撤: {result.max_drawdown:.2f}%")
        report.append(f"最大回撤持续期: {result.max_drawdown_duration} 个周期")
        report.append(f"卡尔玛比率: {result.calmar_ratio:.3f}")

        report.append("\n【交易统计】")
        report.append(f"平均持仓时间: {result.avg_hold_time / 60:.1f} 分钟")
        report.append(f"最大连续盈利: {result.max_consecutive_wins}")
        report.append(f"最大连续亏损: {result.max_consecutive_losses}")

        report.append("\n【资金曲线】")
        report.append(f"初始资金: ${self.config.initial_capital:.2f}")
        report.append(f"最终资金: ${self.equity_curve[-1]:.2f}")
        report.append(f"最高资金: ${max(self.equity_curve):.2f}")
        report.append(f"最低资金: ${min(self.equity_curve):.2f}")

        report.append("\n【退出原因统计】")
        exit_reasons = {}
        for trade in self.closed_trades:
            reason = trade.exit_reason or 'unknown'
            exit_reasons[reason] = exit_reasons.get(reason, 0) + 1

        for reason, count in exit_reasons.items():
            report.append(f"{reason}: {count} ({count/result.total_trades:.1%})")

        report.append("\n" + "=" * 80)

        return "\n".join(report)

    def export_trades_to_csv(self, filename: str):
        """导出交易记录到CSV"""
        if not self.closed_trades:
            print("没有交易记录")
            return

        trades_data = []
        for trade in self.closed_trades:
            trades_data.append({
                'timestamp': datetime.fromtimestamp(trade.timestamp / 1000).strftime('%Y-%m-%d %H:%M:%S'),
                'symbol': trade.symbol,
                'side': trade.side,
                'entry_price': trade.entry_price,
                'exit_price': trade.exit_price,
                'size': trade.size,
                'pnl': trade.pnl,
                'pnl_pct': trade.pnl_pct,
                'exit_reason': trade.exit_reason,
                'hold_time_minutes': trade.hold_time / 60
            })

        df = pd.DataFrame(trades_data)
        df.to_csv(filename, index=False)
        print(f"交易记录已导出到: {filename}")

    def export_equity_curve_to_csv(self, filename: str):
        """导出权益曲线到CSV"""
        if not self.equity_curve or not self.timestamps:
            print("没有权益曲线数据")
            return

        equity_data = []
        for i, (timestamp, equity) in enumerate(zip(self.timestamps, self.equity_curve[1:])):
            equity_data.append({
                'timestamp': datetime.fromtimestamp(timestamp / 1000).strftime('%Y-%m-%d %H:%M:%S'),
                'equity': equity,
                'return_pct': ((equity - self.config.initial_capital) / self.config.initial_capital) * 100
            })

        df = pd.DataFrame(equity_data)
        df.to_csv(filename, index=False)
        print(f"权益曲线已导出到: {filename}")


def backtest_from_ml_data(data_path: str, model_path: str, config: BacktestConfig = None):
    """
    从ML数据和模型运行回测

    Args:
        data_path: 数据文件路径
        model_path: 模型文件路径
        config: 回测配置
    """
    import pickle

    # 加载数据
    print(f"加载数据: {data_path}")
    data = pd.read_csv(data_path)
    data = data[data['label'].notna()].copy()

    # 加载模型
    print(f"加载模型: {model_path}")
    with open(model_path, 'rb') as f:
        model_data = pickle.load(f)

    model = model_data['model']
    feature_names = model_data['feature_names']

    # 准备特征
    X = data[feature_names].fillna(0)

    # 预测
    print("生成预测...")
    predictions = model.predict(X)

    # 创建回测器
    backtester = AdvancedBacktester(config)

    # 运行回测
    print("运行回测...")
    for i in range(len(data)):
        row = data.iloc[i]
        timestamp = int(row['timestamp'])
        price = row['mid_price']
        pred_prob = predictions[i]

        # 生成信号
        if pred_prob > 0.6:
            signal = 'long'
        elif pred_prob < 0.4:
            signal = 'short'
        else:
            signal = 'hold'

        backtester.process_signal(timestamp, 'BTC-USDT-SWAP', signal, price, pred_prob)

    # 平掉所有持仓
    if backtester.positions:
        last_price = data.iloc[-1]['mid_price']
        last_timestamp = int(data.iloc[-1]['timestamp'])
        for trade in backtester.positions[:]:
            backtester.close_position(trade, last_timestamp, last_price, 'backtest_end')

    # 计算指标
    print("\n计算回测指标...")
    result = backtester.calculate_metrics()

    # 生成报告
    report = backtester.generate_report(result)
    print(report)

    # 导出数据
    backtester.export_trades_to_csv('backtest_trades.csv')
    backtester.export_equity_curve_to_csv('backtest_equity.csv')

    return backtester, result


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='高级回测引擎')
    parser.add_argument('--data', required=True, help='数据文件路径')
    parser.add_argument('--model', required=True, help='模型文件路径')
    parser.add_argument('--capital', type=float, default=10000, help='初始资金')
    parser.add_argument('--position-size', type=float, default=100, help='单笔交易金额')
    parser.add_argument('--leverage', type=float, default=10, help='杠杆倍数')
    parser.add_argument('--maker-fee', type=float, default=0.0002, help='Maker手续费')
    parser.add_argument('--taker-fee', type=float, default=0.0005, help='Taker手续费')
    parser.add_argument('--slippage', type=float, default=0.0001, help='滑点')
    parser.add_argument('--stop-loss', type=float, default=0.02, help='止损百分比')
    parser.add_argument('--take-profit', type=float, default=0.03, help='止盈百分比')

    args = parser.parse_args()

    config = BacktestConfig(
        initial_capital=args.capital,
        position_size=args.position_size,
        leverage=args.leverage,
        maker_fee=args.maker_fee,
        taker_fee=args.taker_fee,
        slippage=args.slippage,
        stop_loss_pct=args.stop_loss,
        take_profit_pct=args.take_profit
    )

    backtest_from_ml_data(args.data, args.model, config)
