#!/usr/bin/env python3
"""
回测数据可视化工具

生成专业的回测图表：
- 权益曲线
- 回撤曲线
- 月度收益热力图
- 交易分布图
- 盈亏分布
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.gridspec import GridSpec
import seaborn as sns
from datetime import datetime
from typing import List, Optional
import warnings

warnings.filterwarnings('ignore')

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['figure.figsize'] = (16, 12)
plt.rcParams['figure.dpi'] = 100

# 设置seaborn样式
sns.set_style('whitegrid')
sns.set_palette('husl')


class BacktestVisualizer:
    """回测可视化器"""

    def __init__(self, equity_curve_path: str = 'backtest_equity.csv',
                 trades_path: str = 'backtest_trades.csv'):
        """
        初始化

        Args:
            equity_curve_path: 权益曲线CSV路径
            trades_path: 交易记录CSV路径
        """
        self.equity_df = pd.read_csv(equity_curve_path)
        self.trades_df = pd.read_csv(trades_path)

        # 转换时间戳
        self.equity_df['timestamp'] = pd.to_datetime(self.equity_df['timestamp'])
        self.trades_df['timestamp'] = pd.to_datetime(self.trades_df['timestamp'])

    def plot_equity_curve(self, ax=None):
        """绘制权益曲线"""
        if ax is None:
            fig, ax = plt.subplots(figsize=(12, 6))

        ax.plot(self.equity_df['timestamp'], self.equity_df['equity'],
                linewidth=2, label='权益曲线', color='#2E86AB')
        ax.fill_between(self.equity_df['timestamp'], self.equity_df['equity'],
                        alpha=0.3, color='#2E86AB')

        # 添加初始资金线
        initial_capital = self.equity_df['equity'].iloc[0]
        ax.axhline(y=initial_capital, color='gray', linestyle='--',
                  linewidth=1, label=f'初始资金: ${initial_capital:.2f}')

        ax.set_title('权益曲线', fontsize=14, fontweight='bold')
        ax.set_xlabel('时间', fontsize=12)
        ax.set_ylabel('权益 ($)', fontsize=12)
        ax.legend(loc='best')
        ax.grid(True, alpha=0.3)

        # 格式化x轴
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d %H:%M'))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')

        return ax

    def plot_drawdown(self, ax=None):
        """绘制回撤曲线"""
        if ax is None:
            fig, ax = plt.subplots(figsize=(12, 6))

        # 计算回撤
        equity = self.equity_df['equity'].values
        running_max = np.maximum.accumulate(equity)
        drawdown = (equity - running_max) / running_max * 100

        ax.fill_between(self.equity_df['timestamp'], drawdown, 0,
                        alpha=0.5, color='#A23B72', label='回撤')
        ax.plot(self.equity_df['timestamp'], drawdown,
                linewidth=1.5, color='#A23B72')

        # 标注最大回撤
        max_dd_idx = np.argmin(drawdown)
        max_dd = drawdown[max_dd_idx]
        ax.scatter(self.equity_df['timestamp'].iloc[max_dd_idx], max_dd,
                  color='red', s=100, zorder=5, label=f'最大回撤: {max_dd:.2f}%')

        ax.set_title('回撤曲线', fontsize=14, fontweight='bold')
        ax.set_xlabel('时间', fontsize=12)
        ax.set_ylabel('回撤 (%)', fontsize=12)
        ax.legend(loc='best')
        ax.grid(True, alpha=0.3)

        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')

        return ax

    def plot_monthly_returns(self, ax=None):
        """绘制月度收益热力图"""
        # 添加月份列
        equity_df = self.equity_df.copy()
        equity_df['year'] = equity_df['timestamp'].dt.year
        equity_df['month'] = equity_df['timestamp'].dt.month

        # 计算月度收益
        monthly_returns = equity_df.groupby(['year', 'month']).agg({
            'equity': ['first', 'last']
        })
        monthly_returns['return'] = (monthly_returns[('equity', 'last')] -
                                     monthly_returns[('equity', 'first')]) / \
                                    monthly_returns[('equity', 'first')] * 100

        # 重塑为透视表
        pivot_table = monthly_returns['return'].reset_index().pivot(
            index='year', columns='month', values='return'
        )

        if ax is None:
            fig, ax = plt.subplots(figsize=(12, 6))

        # 绘制热力图
        sns.heatmap(pivot_table, annot=True, fmt='.2f', cmap='RdYlGn',
                   center=0, cbar_kws={'label': '收益率 (%)'}, ax=ax,
                   linewidths=0.5, linecolor='gray')

        ax.set_title('月度收益热力图', fontsize=14, fontweight='bold')
        ax.set_xlabel('月份', fontsize=12)
        ax.set_ylabel('年份', fontsize=12)

        return ax

    def plot_trade_distribution(self, ax=None):
        """绘制交易分布图"""
        if ax is None:
            fig, ax = plt.subplots(figsize=(12, 6))

        # 按时间绘制盈亏
        colors = ['green' if pnl > 0 else 'red' for pnl in self.trades_df['pnl']]
        ax.bar(range(len(self.trades_df)), self.trades_df['pnl'],
               color=colors, alpha=0.7, edgecolor='black', linewidth=0.5)

        # 添加累积盈亏线
        cumulative_pnl = self.trades_df['pnl'].cumsum()
        ax2 = ax.twinx()
        ax2.plot(range(len(self.trades_df)), cumulative_pnl,
                color='#2E86AB', linewidth=2, label='累积盈亏', marker='o', markersize=3)
        ax2.set_ylabel('累积盈亏 ($)', fontsize=12)
        ax2.legend(loc='upper left')
        ax2.grid(False)

        ax.set_title('交易盈亏分布', fontsize=14, fontweight='bold')
        ax.set_xlabel('交易序号', fontsize=12)
        ax.set_ylabel('单笔盈亏 ($)', fontsize=12)
        ax.axhline(y=0, color='black', linestyle='-', linewidth=0.8)
        ax.grid(True, alpha=0.3, axis='y')

        return ax

    def plot_pnl_histogram(self, ax=None):
        """绘制盈亏分布直方图"""
        if ax is None:
            fig, ax = plt.subplots(figsize=(12, 6))

        # 分离盈利和亏损
        wins = self.trades_df[self.trades_df['pnl'] > 0]['pnl']
        losses = self.trades_df[self.trades_df['pnl'] < 0]['pnl']

        # 绘制直方图
        ax.hist(wins, bins=30, alpha=0.7, color='green', label=f'盈利交易 (n={len(wins)})', edgecolor='black')
        ax.hist(losses, bins=30, alpha=0.7, color='red', label=f'亏损交易 (n={len(losses)})', edgecolor='black')

        # 添加均值线
        ax.axvline(x=wins.mean(), color='darkgreen', linestyle='--',
                  linewidth=2, label=f'平均盈利: ${wins.mean():.2f}')
        ax.axvline(x=losses.mean(), color='darkred', linestyle='--',
                  linewidth=2, label=f'平均亏损: ${losses.mean():.2f}')

        ax.set_title('盈亏分布直方图', fontsize=14, fontweight='bold')
        ax.set_xlabel('盈亏 ($)', fontsize=12)
        ax.set_ylabel('交易次数', fontsize=12)
        ax.legend(loc='best')
        ax.grid(True, alpha=0.3, axis='y')

        return ax

    def plot_holding_time_distribution(self, ax=None):
        """绘制持仓时间分布"""
        if ax is None:
            fig, ax = plt.subplots(figsize=(12, 6))

        hold_times_minutes = self.trades_df['hold_time_minutes']

        # 绘制直方图
        ax.hist(hold_times_minutes, bins=50, alpha=0.7, color='#F18F01', edgecolor='black')

        # 添加均值线
        mean_hold_time = hold_times_minutes.mean()
        ax.axvline(x=mean_hold_time, color='red', linestyle='--',
                  linewidth=2, label=f'平均持仓时间: {mean_hold_time:.1f} 分钟')

        ax.set_title('持仓时间分布', fontsize=14, fontweight='bold')
        ax.set_xlabel('持仓时间 (分钟)', fontsize=12)
        ax.set_ylabel('交易次数', fontsize=12)
        ax.legend(loc='best')
        ax.grid(True, alpha=0.3, axis='y')

        return ax

    def plot_exit_reason_pie(self, ax=None):
        """绘制退出原因饼图"""
        if ax is None:
            fig, ax = plt.subplots(figsize=(8, 8))

        exit_reasons = self.trades_df['exit_reason'].value_counts()

        colors = sns.color_palette('husl', len(exit_reasons))
        wedges, texts, autotexts = ax.pie(exit_reasons.values,
                                          labels=exit_reasons.index,
                                          autopct='%1.1f%%',
                                          startangle=90,
                                          colors=colors,
                                          explode=[0.05] * len(exit_reasons))

        # 美化文字
        for text in texts:
            text.set_fontsize(12)
            text.set_fontweight('bold')

        for autotext in autotexts:
            autotext.set_color('white')
            autotext.set_fontsize(10)
            autotext.set_fontweight('bold')

        ax.set_title('交易退出原因分布', fontsize=14, fontweight='bold')

        return ax

    def plot_win_loss_by_side(self, ax=None):
        """绘制多空胜率对比"""
        if ax is None:
            fig, ax = plt.subplots(figsize=(10, 6))

        # 统计多空胜率
        side_stats = []
        for side in self.trades_df['side'].unique():
            side_trades = self.trades_df[self.trades_df['side'] == side]
            wins = len(side_trades[side_trades['pnl'] > 0])
            total = len(side_trades)
            win_rate = wins / total if total > 0 else 0
            avg_pnl = side_trades['pnl'].mean()

            side_stats.append({
                'side': side,
                'win_rate': win_rate * 100,
                'avg_pnl': avg_pnl,
                'total_trades': total
            })

        stats_df = pd.DataFrame(side_stats)

        # 绘制柱状图
        x = np.arange(len(stats_df))
        width = 0.35

        ax.bar(x - width/2, stats_df['win_rate'], width, label='胜率 (%)',
               color='#2E86AB', alpha=0.8, edgecolor='black')
        ax.bar(x + width/2, stats_df['avg_pnl'], width, label='平均盈亏 ($)',
               color='#F18F01', alpha=0.8, edgecolor='black')

        ax.set_xlabel('交易方向', fontsize=12)
        ax.set_ylabel('值', fontsize=12)
        ax.set_title('多空胜率与盈亏对比', fontsize=14, fontweight='bold')
        ax.set_xticks(x)
        ax.set_xticklabels(stats_df['side'])
        ax.legend()
        ax.grid(True, alpha=0.3, axis='y')

        # 添加数值标签
        for i, (wr, pnl) in enumerate(zip(stats_df['win_rate'], stats_df['avg_pnl'])):
            ax.text(i - width/2, wr, f'{wr:.1f}%', ha='center', va='bottom', fontweight='bold')
            ax.text(i + width/2, pnl, f'${pnl:.2f}', ha='center', va='bottom', fontweight='bold')

        return ax

    def create_comprehensive_report(self, output_path: str = 'backtest_report.png'):
        """创建综合报告"""
        # 创建大图
        fig = plt.figure(figsize=(20, 16))
        gs = GridSpec(4, 2, figure=fig, hspace=0.3, wspace=0.3)

        # 1. 权益曲线
        ax1 = fig.add_subplot(gs[0, :])
        self.plot_equity_curve(ax1)

        # 2. 回撤曲线
        ax2 = fig.add_subplot(gs[1, :])
        self.plot_drawdown(ax2)

        # 3. 交易分布
        ax3 = fig.add_subplot(gs[2, :])
        self.plot_trade_distribution(ax3)

        # 4. 盈亏分布
        ax4 = fig.add_subplot(gs[3, 0])
        self.plot_pnl_histogram(ax4)

        # 5. 退出原因
        ax5 = fig.add_subplot(gs[3, 1])
        self.plot_exit_reason_pie(ax5)

        plt.suptitle('回测综合报告', fontsize=18, fontweight='bold', y=0.995)

        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        print(f"综合报告已保存到: {output_path}")

        plt.show()

    def create_detailed_analysis(self, output_path: str = 'backtest_analysis.png'):
        """创建详细分析图"""
        fig = plt.figure(figsize=(20, 12))
        gs = GridSpec(3, 2, figure=fig, hspace=0.3, wspace=0.3)

        # 1. 月度收益热力图
        ax1 = fig.add_subplot(gs[0, :])
        self.plot_monthly_returns(ax1)

        # 2. 持仓时间分布
        ax2 = fig.add_subplot(gs[1, 0])
        self.plot_holding_time_distribution(ax2)

        # 3. 多空对比
        ax3 = fig.add_subplot(gs[1, 1])
        self.plot_win_loss_by_side(ax3)

        # 4. 盈亏分布
        ax4 = fig.add_subplot(gs[2, 0])
        self.plot_pnl_histogram(ax4)

        # 5. 退出原因
        ax5 = fig.add_subplot(gs[2, 1])
        self.plot_exit_reason_pie(ax5)

        plt.suptitle('回测详细分析', fontsize=18, fontweight='bold', y=0.995)

        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        print(f"详细分析已保存到: {output_path}")

        plt.show()


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description='回测数据可视化')
    parser.add_argument('--equity', default='backtest_equity.csv', help='权益曲线CSV路径')
    parser.add_argument('--trades', default='backtest_trades.csv', help='交易记录CSV路径')
    parser.add_argument('--output', default='backtest_report.png', help='输出图片路径')

    args = parser.parse_args()

    # 创建可视化器
    visualizer = BacktestVisualizer(args.equity, args.trades)

    # 生成报告
    visualizer.create_comprehensive_report(args.output)
    visualizer.create_detailed_analysis('backtest_analysis.png')


if __name__ == '__main__':
    main()
