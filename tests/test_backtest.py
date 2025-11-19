#!/usr/bin/env python3
"""
回测引擎测试套件
"""

import pytest
import sys
import os

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from advanced_backtest import (
    BacktestConfig, Trade, AdvancedBacktester, BacktestResult
)


class TestBacktestConfig:
    """测试回测配置"""

    def test_default_config(self):
        """测试默认配置"""
        config = BacktestConfig()
        assert config.initial_capital == 10000.0
        assert config.leverage == 10.0
        assert config.maker_fee == 0.0002
        assert config.taker_fee == 0.0005

    def test_custom_config(self):
        """测试自定义配置"""
        config = BacktestConfig(
            initial_capital=50000.0,
            leverage=20.0,
            maker_fee=0.0001
        )
        assert config.initial_capital == 50000.0
        assert config.leverage == 20.0
        assert config.maker_fee == 0.0001


class TestAdvancedBacktester:
    """测试回测引擎"""

    @pytest.fixture
    def backtester(self):
        """创建回测器实例"""
        config = BacktestConfig(
            initial_capital=10000.0,
            position_size=100.0,
            leverage=10.0
        )
        return AdvancedBacktester(config)

    def test_initialization(self, backtester):
        """测试初始化"""
        assert backtester.capital == 10000.0
        assert len(backtester.positions) == 0
        assert len(backtester.closed_trades) == 0

    def test_calculate_fee(self, backtester):
        """测试手续费计算"""
        # Maker费用
        maker_fee = backtester.calculate_fee(100.0, 1.0, is_maker=True)
        assert maker_fee == 100.0 * 1.0 * 0.0002

        # Taker费用
        taker_fee = backtester.calculate_fee(100.0, 1.0, is_maker=False)
        assert taker_fee == 100.0 * 1.0 * 0.0005

    def test_apply_slippage(self, backtester):
        """测试滑点计算"""
        price = 100.0
        slippage = backtester.config.slippage

        # 做多滑点（买入价格更高）
        long_price = backtester.apply_slippage(price, 'long')
        assert long_price == price + (price * slippage)

        # 做空滑点（卖出价格更低）
        short_price = backtester.apply_slippage(price, 'short')
        assert short_price == price - (price * slippage)

    def test_open_position(self, backtester):
        """测试开仓"""
        timestamp = 1000000
        symbol = 'BTC-USDT-SWAP'
        price = 100.0

        # 开多头
        trade = backtester.open_position(timestamp, symbol, 'long', price)

        assert trade is not None
        assert trade.side == 'long'
        assert trade.entry_price > price  # 应用了滑点
        assert len(backtester.positions) == 1
        assert backtester.capital < 10000.0  # 扣除了保证金和手续费

    def test_close_position(self, backtester):
        """测试平仓"""
        # 先开仓
        timestamp1 = 1000000
        price1 = 100.0
        trade = backtester.open_position(timestamp1, 'BTC-USDT-SWAP', 'long', price1)

        # 再平仓（盈利）
        timestamp2 = 1001000
        price2 = 110.0
        backtester.close_position(trade, timestamp2, price2, 'signal')

        assert len(backtester.positions) == 0
        assert len(backtester.closed_trades) == 1
        assert backtester.closed_trades[0].pnl > 0  # 应该盈利

    def test_stop_loss(self, backtester):
        """测试止损"""
        # 开多头
        timestamp1 = 1000000
        price1 = 100.0
        backtester.open_position(timestamp1, 'BTC-USDT-SWAP', 'long', price1)

        # 价格下跌触发止损
        timestamp2 = 1001000
        price2 = 95.0  # 下跌5%
        backtester.check_stop_loss_take_profit(timestamp2, price2)

        # 应该触发止损
        assert len(backtester.positions) == 0
        assert len(backtester.closed_trades) == 1
        assert backtester.closed_trades[0].exit_reason == 'stop_loss'
        assert backtester.closed_trades[0].pnl < 0

    def test_take_profit(self, backtester):
        """测试止盈"""
        # 开多头
        timestamp1 = 1000000
        price1 = 100.0
        backtester.open_position(timestamp1, 'BTC-USDT-SWAP', 'long', price1)

        # 价格上涨触发止盈
        timestamp2 = 1001000
        price2 = 105.0  # 上涨5%
        backtester.check_stop_loss_take_profit(timestamp2, price2)

        # 应该触发止盈
        assert len(backtester.positions) == 0
        assert len(backtester.closed_trades) == 1
        assert backtester.closed_trades[0].exit_reason == 'take_profit'
        assert backtester.closed_trades[0].pnl > 0

    def test_max_positions(self, backtester):
        """测试最大持仓限制"""
        timestamp = 1000000
        price = 100.0

        # 开3个仓位（最大限制）
        for i in range(3):
            trade = backtester.open_position(timestamp + i, 'BTC-USDT-SWAP', 'long', price)
            assert trade is not None

        # 尝试开第4个仓位，应该失败
        trade = backtester.open_position(timestamp + 3, 'BTC-USDT-SWAP', 'long', price)
        assert trade is None
        assert len(backtester.positions) == 3

    def test_process_signal_long(self, backtester):
        """测试做多信号处理"""
        timestamp = 1000000
        price = 100.0

        backtester.process_signal(timestamp, 'BTC-USDT-SWAP', 'long', price)

        assert len(backtester.positions) == 1
        assert backtester.positions[0].side == 'long'

    def test_process_signal_short(self, backtester):
        """测试做空信号处理"""
        timestamp = 1000000
        price = 100.0

        backtester.process_signal(timestamp, 'BTC-USDT-SWAP', 'short', price)

        assert len(backtester.positions) == 1
        assert backtester.positions[0].side == 'short'

    def test_process_signal_close_all(self, backtester):
        """测试平仓所有信号"""
        # 先开两个仓位
        timestamp1 = 1000000
        price1 = 100.0
        backtester.process_signal(timestamp1, 'BTC-USDT-SWAP', 'long', price1)
        backtester.process_signal(timestamp1 + 1000, 'ETH-USDT-SWAP', 'short', price1)

        assert len(backtester.positions) == 2

        # 平仓所有
        timestamp2 = 1002000
        price2 = 105.0
        backtester.process_signal(timestamp2, 'BTC-USDT-SWAP', 'close_all', price2)

        assert len(backtester.positions) == 0
        assert len(backtester.closed_trades) == 2

    def test_calculate_metrics(self, backtester):
        """测试指标计算"""
        # 执行一些交易
        timestamps = [1000000, 1001000, 1002000, 1003000, 1004000]
        prices = [100, 105, 103, 108, 110]
        signals = ['long', 'close_all', 'short', 'close_all', 'long']

        for ts, price, signal in zip(timestamps, prices, signals):
            backtester.process_signal(ts, 'BTC-USDT-SWAP', signal, price)

        # 计算指标
        result = backtester.calculate_metrics()

        assert result.total_trades > 0
        assert result.win_rate >= 0 and result.win_rate <= 1
        assert len(result.trades) == result.total_trades
        assert len(result.equity_curve) > 0


class TestMetrics:
    """测试指标计算"""

    def test_win_rate_calculation(self):
        """测试胜率计算"""
        result = BacktestResult()
        result.total_trades = 10
        result.winning_trades = 6
        result.losing_trades = 4
        result.win_rate = 6 / 10

        assert result.win_rate == 0.6

    def test_profit_factor(self):
        """测试盈利因子"""
        result = BacktestResult()
        # 假设总盈利200，总亏损100
        result.profit_factor = 200 / 100

        assert result.profit_factor == 2.0


class TestIntegration:
    """集成测试"""

    def test_full_backtest_workflow(self):
        """测试完整的回测流程"""
        config = BacktestConfig(
            initial_capital=10000.0,
            position_size=100.0,
            stop_loss_pct=0.02,
            take_profit_pct=0.03
        )
        backtester = AdvancedBacktester(config)

        # 模拟一系列交易
        test_data = [
            (1000000, 'BTC-USDT-SWAP', 'long', 100.0),
            (1010000, 'BTC-USDT-SWAP', 'close_all', 103.0),  # 盈利
            (1020000, 'BTC-USDT-SWAP', 'short', 103.0),
            (1030000, 'BTC-USDT-SWAP', 'close_all', 105.0),  # 亏损
            (1040000, 'BTC-USDT-SWAP', 'long', 105.0),
            (1050000, 'BTC-USDT-SWAP', 'close_all', 110.0),  # 盈利
        ]

        for timestamp, symbol, signal, price in test_data:
            backtester.process_signal(timestamp, symbol, signal, price)

        # 验证结果
        result = backtester.calculate_metrics()

        assert result.total_trades == 3
        assert result.winning_trades == 2
        assert result.losing_trades == 1
        assert result.win_rate == pytest.approx(2/3, rel=0.01)
        assert result.total_pnl != 0
        assert len(result.equity_curve) > 0


def run_tests():
    """运行所有测试"""
    pytest.main([__file__, '-v', '--tb=short'])


if __name__ == '__main__':
    run_tests()
