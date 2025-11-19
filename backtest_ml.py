#!/usr/bin/env python3
"""
机器学习策略回测工具

使用历史数据回测ML模型的表现
"""

import pandas as pd
import numpy as np
import pickle
import argparse
from pathlib import Path

def load_model(model_path):
    """加载模型"""
    with open(model_path, 'rb') as f:
        model_data = pickle.load(f)
    return model_data['model'], model_data['feature_names']

def backtest(data_path, model_path, initial_capital=1000, trade_amount=50, threshold=0.6):
    """
    回测函数

    Args:
        data_path: 数据文件路径
        model_path: 模型文件路径
        initial_capital: 初始资金
        trade_amount: 每笔交易金额
        threshold: 预测置信度阈值
    """
    # 加载数据
    print(f"加载数据: {data_path}")
    data = pd.read_csv(data_path)

    # 过滤有标签的数据
    data = data[data['label'].notna()].copy()
    print(f"总样本数: {len(data)}")

    # 加载模型
    print(f"加载模型: {model_path}")
    model, feature_names = load_model(model_path)

    # 准备特征
    X = data[feature_names].fillna(0)
    y_true = data['label'].values

    # 预测
    print("开始预测...")
    y_pred_prob = model.predict(X)
    y_pred = (y_pred_prob > 0.5).astype(int)

    # 回测
    print(f"\n{'='*60}")
    print("回测开始")
    print(f"{'='*60}")

    capital = initial_capital
    positions = []  # 持仓记录
    trades = []     # 交易记录

    for i in range(len(data)):
        prob = y_pred_prob[i]
        prediction = y_pred[i]
        actual = y_true[i]
        price = data.iloc[i]['mid_price']

        # 交易决策
        action = None

        if prediction == 1 and prob > threshold:
            action = 'BUY'
        elif prediction == 0 and prob < (1 - threshold):
            action = 'SELL'

        if action:
            # 计算盈亏
            if action == 'BUY':
                if actual == 1:  # 预测对了
                    pnl = trade_amount * 0.003  # 假设0.3%的收益
                else:
                    pnl = -trade_amount * 0.003
            else:  # SELL
                if actual == 0:  # 预测对了
                    pnl = trade_amount * 0.003
                else:
                    pnl = -trade_amount * 0.003

            capital += pnl

            trades.append({
                'index': i,
                'action': action,
                'prediction': prediction,
                'actual': actual,
                'prob': prob,
                'price': price,
                'pnl': pnl,
                'capital': capital
            })

    # 统计
    print(f"\n{'='*60}")
    print("回测结果")
    print(f"{'='*60}")

    trades_df = pd.DataFrame(trades)

    if len(trades_df) > 0:
        print(f"\n总交易次数: {len(trades_df)}")
        print(f"初始资金: ${initial_capital:.2f}")
        print(f"最终资金: ${capital:.2f}")
        print(f"总收益: ${capital - initial_capital:.2f}")
        print(f"收益率: {((capital / initial_capital - 1) * 100):.2f}%")

        # 胜率
        win_trades = trades_df[trades_df['pnl'] > 0]
        win_rate = len(win_trades) / len(trades_df) * 100
        print(f"\n胜率: {win_rate:.2f}%")

        # 平均盈亏
        avg_win = win_trades['pnl'].mean() if len(win_trades) > 0 else 0
        lose_trades = trades_df[trades_df['pnl'] < 0]
        avg_loss = lose_trades['pnl'].mean() if len(lose_trades) > 0 else 0
        print(f"平均盈利: ${avg_win:.2f}")
        print(f"平均亏损: ${avg_loss:.2f}")

        # 最大回撤
        capital_series = trades_df['capital']
        running_max = capital_series.cummax()
        drawdown = (capital_series - running_max) / running_max
        max_drawdown = drawdown.min() * 100
        print(f"最大回撤: {max_drawdown:.2f}%")

        # 夏普比率（简化版）
        returns = trades_df['pnl'] / trade_amount
        sharpe = returns.mean() / returns.std() if returns.std() > 0 else 0
        print(f"夏普比率: {sharpe:.3f}")

        # 交易明细（前10笔）
        print(f"\n前10笔交易:")
        print(trades_df[['action', 'prob', 'pnl', 'capital']].head(10).to_string(index=False))

    else:
        print("无交易记录（可能阈值过高）")

    # 模型准确率
    correct = (y_pred == y_true).sum()
    accuracy = correct / len(y_true) * 100
    print(f"\n模型准确率: {accuracy:.2f}%")

    return trades_df

def main():
    parser = argparse.ArgumentParser(description='机器学习策略回测工具')
    parser.add_argument('--data', required=True, help='数据文件路径')
    parser.add_argument('--model', required=True, help='模型文件路径')
    parser.add_argument('--capital', type=float, default=1000, help='初始资金')
    parser.add_argument('--amount', type=float, default=50, help='每笔交易金额')
    parser.add_argument('--threshold', type=float, default=0.6, help='预测置信度阈值')

    args = parser.parse_args()

    # 检查文件存在性
    if not Path(args.data).exists():
        print(f"错误: 数据文件不存在: {args.data}")
        return

    if not Path(args.model).exists():
        print(f"错误: 模型文件不存在: {args.model}")
        return

    # 运行回测
    backtest(args.data, args.model, args.capital, args.amount, args.threshold)

if __name__ == '__main__':
    main()
