"""
高级交易机器人 - 集成所有优化功能
包含：ML预测、智能执行、高级风控、实时监控
"""
import time
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List
import logging

import okx.Trade_api as TradeAPI
import okx.Public_api as PublicAPI
import okx.Market_api as MarketAPI
import okx.Account_api as AccountAPI

from config_manager import ConfigManager
from indicators import TechnicalIndicators
from strategy import StrategyFactory
from order_manager import OrderManager, RetryConfig
from risk_manager import RiskManager, RiskLevel
from utils import setup_logger, FeishuNotifier

# 高级功能模块
from ml_predictor import MLPredictor, SimplePredictor
from execution_optimizer import ExecutionOptimizer, ExecutionStrategy
from advanced_risk import (
    AdvancedRiskManager, StopLossConfig, TakeProfitConfig,
    PositionSizing, StopLossType
)
from monitoring import PerformanceMonitor, AlertLevel


class AdvancedTradingBot:
    """高级交易机器人"""

    def __init__(self, config_path: str = "config.json"):
        """
        初始化高级交易机器人

        Args:
            config_path: 配置文件路径
        """
        # 加载配置
        print("正在加载配置...")
        self.config_manager = ConfigManager(config_path)
        try:
            self.config = self.config_manager.load_config()
        except Exception as e:
            print(f"❌ 配置加载失败: {e}")
            sys.exit(1)

        print("✓ 配置加载成功")

        # 设置日志
        self.logger = setup_logger(
            name='advanced_trading_bot',
            log_file='log/advanced_bot.log',
            level=logging.INFO
        )
        self.logger.info("=" * 60)
        self.logger.info("高级交易机器人启动")
        self.logger.info("=" * 60)

        # 初始化飞书通知
        self.notifier = FeishuNotifier(
            webhook_url=self.config.feishu_webhook,
            enabled=bool(self.config.feishu_webhook)
        )

        # 初始化OKX API
        self._init_okx_api()

        # 获取合约信息
        self.instrument_info: Dict[str, Dict] = {}
        self._fetch_instrument_info()

        # 初始化核心组件
        self.indicator_calculator = TechnicalIndicators(
            cache_ttl=self.config.cache_ttl
        )

        self.strategy = StrategyFactory.create_strategy(
            strategy_type='pinbar',
            indicator_calculator=self.indicator_calculator
        )

        self.order_manager = OrderManager(
            trade_api=self.trade_api,
            market_api=self.market_api,
            public_api=self.public_api,
            account_api=self.account_api,
            instrument_info=self.instrument_info,
            retry_config=RetryConfig(max_retries=3)
        )

        self.risk_manager = RiskManager(
            max_position_size_usdt=self.config.risk.max_position_size_usdt,
            max_total_position_usdt=self.config.risk.max_total_position_usdt,
            max_daily_loss_usdt=self.config.risk.max_daily_loss_usdt,
            max_orders_per_pair=self.config.risk.max_orders_per_pair,
            enable_risk_control=self.config.risk.enable_risk_control
        )

        # 初始化高级组件
        self._init_advanced_components()

        self.logger.info("=" * 60)
        self.logger.info("🚀 高级功能已启用:")
        self.logger.info(f"  ✓ ML预测: {'启用' if self.ml_predictor.enabled else '禁用'}")
        self.logger.info(f"  ✓ 智能执行优化: 启用")
        self.logger.info(f"  ✓ 高级止损/止盈: 启用")
        self.logger.info(f"  ✓ 实时监控: 启用")
        self.logger.info("=" * 60)

        # 统计信息
        self.processed_count = 0
        self.error_count = 0

    def _init_okx_api(self):
        """初始化OKX API"""
        self.logger.info("正在初始化OKX API...")
        okx_cfg = self.config.okx
        self.trade_api = TradeAPI.TradeAPI(
            okx_cfg.api_key, okx_cfg.secret, okx_cfg.password,
            okx_cfg.simulated, '0'
        )
        self.market_api = MarketAPI.MarketAPI(
            okx_cfg.api_key, okx_cfg.secret, okx_cfg.password,
            okx_cfg.simulated, '0'
        )
        self.public_api = PublicAPI.PublicAPI(
            okx_cfg.api_key, okx_cfg.secret, okx_cfg.password,
            okx_cfg.simulated, '0'
        )
        self.account_api = AccountAPI.AccountAPI(
            okx_cfg.api_key, okx_cfg.secret, okx_cfg.password,
            okx_cfg.simulated, '0'
        )

    def _init_advanced_components(self):
        """初始化高级组件"""
        # ML预测器
        try:
            self.ml_predictor = MLPredictor(
                model_type='random_forest',
                confidence_threshold=0.6
            )
            if not self.ml_predictor.enabled:
                self.logger.warning("ML功能不可用，使用简单预测器")
                self.simple_predictor = SimplePredictor()
        except Exception as e:
            self.logger.error(f"ML预测器初始化失败: {e}")
            self.simple_predictor = SimplePredictor()

        # 执行优化器
        self.execution_optimizer = ExecutionOptimizer(
            min_slice_size=10.0,
            max_slices=10,
            default_duration_minutes=5
        )

        # 高级风险管理器
        self.advanced_risk = AdvancedRiskManager(
            account_balance=10000.0,  # 可从配置读取
            stop_loss_config=StopLossConfig(
                enabled=True,
                stop_loss_type=StopLossType.TRAILING,
                trailing_percentage=3.0
            ),
            take_profit_config=TakeProfitConfig(
                enabled=True,
                target_percentage=10.0,
                partial_take_profit=True
            ),
            position_sizing=PositionSizing(
                use_kelly_criterion=False,
                risk_per_trade_percentage=2.0
            )
        )

        # 性能监控器
        self.monitor = PerformanceMonitor(
            history_size=1000,
            alert_callback=self._handle_alert
        )

    def _handle_alert(self, alert):
        """
        处理预警

        Args:
            alert: 预警对象
        """
        # 发送飞书通知
        if alert.level in [AlertLevel.ERROR, AlertLevel.CRITICAL]:
            emoji = "🚨" if alert.level == AlertLevel.CRITICAL else "⚠️"
            self.notifier.send_text(
                f"{emoji} {alert.category.upper()} 预警\n{alert.message}"
            )

    def _fetch_instrument_info(self):
        """获取合约信息"""
        try:
            self.logger.info("正在获取合约信息...")
            response = self.public_api.get_instruments(instType='SWAP')

            if 'data' in response and len(response['data']) > 0:
                self.instrument_info.clear()
                for instrument in response['data']:
                    inst_id = instrument['instId']
                    self.instrument_info[inst_id] = instrument

                self.logger.info(f"✓ 已获取 {len(self.instrument_info)} 个合约信息")
            else:
                raise ValueError("获取合约信息失败")

        except Exception as e:
            self.logger.error(f"❌ 获取合约信息失败: {e}")
            raise

    def process_trading_pair(self, inst_id: str) -> bool:
        """
        处理单个交易对（高级版本）

        Args:
            inst_id: 交易对ID

        Returns:
            是否处理成功
        """
        start_time = time.time()

        try:
            pair_config = self.config.get_pair_config(inst_id)
            if not pair_config:
                return False

            # 风险检查
            should_stop, reason = self.risk_manager.should_stop_trading()
            if should_stop:
                self.logger.warning(f"风险控制: {reason}")
                return False

            should_reduce, reason = self.advanced_risk.should_reduce_risk()
            if should_reduce:
                self.logger.warning(f"高级风控建议: {reason}")

            self.logger.info(f"\n{'='*60}")
            self.logger.info(f"处理交易对: {inst_id}")
            self.logger.info(f"{'='*60}")

            # 获取市场数据
            api_start = time.time()
            current_price = self.order_manager.get_mark_price(inst_id)
            klines = self.order_manager.get_historical_klines(inst_id)
            api_time = (time.time() - api_start) * 1000

            # 记录API调用
            self.monitor.record_api_call(True, api_time)

            # 生成交易信号
            signal = self.strategy.generate_signal(
                inst_id=inst_id,
                current_price=current_price,
                klines=klines,
                config={
                    'ema_period': pair_config.ema_period,
                    'ema_enabled': pair_config.ema_enabled,
                    'value_multiplier': pair_config.value_multiplier
                }
            )

            # ML增强预测（可选）
            ml_prediction = None
            if hasattr(self, 'ml_predictor') and self.ml_predictor.enabled:
                ml_prediction = self.ml_predictor.predict(
                    inst_id=inst_id,
                    klines=klines,
                    current_price=current_price,
                    ema=signal.metadata.get('ema', 0),
                    atr=signal.metadata.get('atr', 0),
                    amplitude=signal.metadata.get('average_amplitude', 0)
                )

                if ml_prediction and ml_prediction.confidence > 0.6:
                    self.logger.info(
                        f"{inst_id}: ML预测 - {ml_prediction.direction} "
                        f"(置信度: {ml_prediction.confidence:.2f})"
                    )

            # 撤销旧订单
            self.order_manager.cancel_all_orders(inst_id)
            self.risk_manager.clear_orders(inst_id)

            # 执行交易
            orders_placed = 0

            # 做多单
            if signal.should_long:
                if self._should_enter_position(signal.should_long, ml_prediction, 'bullish'):
                    amount = self._calculate_position_size(
                        inst_id=inst_id,
                        entry_price=signal.long_price,
                        side='long',
                        atr=signal.metadata.get('atr', 0),
                        default_amount=pair_config.long_amount_usdt
                    )

                    if self._place_order_with_execution_optimization(
                        inst_id=inst_id,
                        side='buy',
                        price=signal.long_price,
                        amount_usdt=amount,
                        leverage=self.config.leverage
                    ):
                        orders_placed += 1

            # 做空单
            if signal.should_short:
                if self._should_enter_position(signal.should_short, ml_prediction, 'bearish'):
                    amount = self._calculate_position_size(
                        inst_id=inst_id,
                        entry_price=signal.short_price,
                        side='short',
                        atr=signal.metadata.get('atr', 0),
                        default_amount=pair_config.short_amount_usdt
                    )

                    if self._place_order_with_execution_optimization(
                        inst_id=inst_id,
                        side='sell',
                        price=signal.short_price,
                        amount_usdt=amount,
                        leverage=self.config.leverage
                    ):
                        orders_placed += 1

            elapsed = time.time() - start_time
            self.logger.info(
                f"{inst_id}: 处理完成 (下单: {orders_placed}, "
                f"耗时: {elapsed:.2f}s)"
            )

            return True

        except Exception as e:
            error_msg = f"{inst_id}: 处理异常 - {e}"
            self.logger.error(error_msg, exc_info=True)
            self.notifier.notify_error(str(e), inst_id)
            self.monitor.record_api_call(False, 0)
            self.error_count += 1
            return False

    def _should_enter_position(self, signal_direction, ml_prediction, expected_direction):
        """
        综合判断是否应该进场

        Args:
            signal_direction: 策略信号方向
            ml_prediction: ML预测结果
            expected_direction: 预期方向

        Returns:
            是否应该进场
        """
        # 基本信号
        if not signal_direction:
            return False

        # 如果有ML预测，结合判断
        if ml_prediction and ml_prediction.confidence > 0.6:
            if ml_prediction.direction != expected_direction:
                self.logger.info(f"ML预测与策略不一致，跳过")
                return False

        return True

    def _calculate_position_size(
        self,
        inst_id: str,
        entry_price: float,
        side: str,
        atr: float,
        default_amount: float
    ) -> float:
        """
        计算仓位大小

        Args:
            inst_id: 交易对ID
            entry_price: 入场价格
            side: 方向
            atr: ATR值
            default_amount: 默认金额

        Returns:
            建议仓位大小
        """
        # 计算止损价格
        position_side = 'long' if side == 'buy' else 'short'
        stop_price = self.advanced_risk.calculate_stop_loss_price(
            inst_id=inst_id,
            entry_price=entry_price,
            position_side=position_side,
            atr=atr
        )

        # 使用高级仓位计算
        if stop_price > 0:
            recommended_size = self.advanced_risk.calculate_position_size(
                inst_id=inst_id,
                entry_price=entry_price,
                stop_loss_price=stop_price
            )

            # 取推荐值和配置值的较小值
            return min(recommended_size, default_amount)

        return default_amount

    def _place_order_with_execution_optimization(
        self,
        inst_id: str,
        side: str,
        price: float,
        amount_usdt: float,
        leverage: int
    ) -> bool:
        """
        使用执行优化下单

        Args:
            inst_id: 交易对ID
            side: 方向
            price: 价格
            amount_usdt: 金额
            leverage: 杠杆

        Returns:
            是否成功
        """
        # 检查是否需要拆分订单
        if self.execution_optimizer.should_split_order(amount_usdt):
            self.logger.info(f"{inst_id}: 使用智能执行优化（金额较大）")
            # 创建TWAP执行计划
            plan = self.execution_optimizer.create_twap_plan(
                inst_id=inst_id,
                total_amount=amount_usdt,
                duration_minutes=3
            )
            # 注：实际执行会在后台进行，这里只是创建计划
            # 简化起见，先执行第一个切片
            slice_order = plan.slices[0] if plan.slices else None
            if slice_order:
                amount_usdt = slice_order.size

        # 风险检查
        can_order, reason = self.risk_manager.can_place_order(
            inst_id, amount_usdt, side
        )
        if not can_order:
            self.logger.warning(f"{inst_id}: {reason}")
            return False

        # 下单
        result = self.order_manager.place_limit_order(
            inst_id=inst_id,
            side=side,
            price=price,
            amount_usdt=amount_usdt,
            leverage=leverage
        )

        if result:
            self.risk_manager.record_order(inst_id)

            # 添加止损订单
            position_side = 'long' if side == 'buy' else 'short'
            self.advanced_risk.add_stop_loss_order(
                inst_id=inst_id,
                entry_price=price,
                position_side=position_side,
                size_usdt=amount_usdt
            )

            return True

        return False

    def run_cycle(self):
        """运行交易周期"""
        start_time = time.time()
        inst_ids = self.config.get_all_inst_ids()
        total = len(inst_ids)

        self.logger.info(f"\n{'#'*60}")
        self.logger.info(f"开始新的交易周期 (共 {total} 个交易对)")
        self.logger.info(f"{'#'*60}")

        # 批量处理
        success_count = 0
        batch_size = self.config.batch_size

        for i in range(0, total, batch_size):
            batch = inst_ids[i:i + batch_size]
            with ThreadPoolExecutor(max_workers=batch_size) as executor:
                futures = {
                    executor.submit(self.process_trading_pair, inst_id): inst_id
                    for inst_id in batch
                }

                for future in as_completed(futures):
                    try:
                        if future.result():
                            success_count += 1
                            self.processed_count += 1
                    except Exception as e:
                        self.logger.error(f"处理失败: {e}")

        elapsed = time.time() - start_time
        self.logger.info(f"\n{'#'*60}")
        self.logger.info(
            f"周期完成: 成功 {success_count}/{total}, "
            f"耗时 {elapsed:.2f}秒"
        )

        # 显示监控报告
        perf_report = self.monitor.get_performance_report()
        sys_report = self.monitor.get_system_report()
        self.logger.info("\n📊 性能报告:")
        for key, value in perf_report.items():
            self.logger.info(f"  {key}: {value}")

        self.logger.info("\n💻 系统报告:")
        for key, value in sys_report.items():
            self.logger.info(f"  {key}: {value}")

        self.logger.info(f"{'#'*60}\n")

    def run(self):
        """运行机器人"""
        self.logger.info("高级交易机器人开始运行...")
        self.notifier.send_text("🚀 高级交易机器人已启动（包含ML预测、智能执行、高级风控）")

        try:
            while True:
                try:
                    self.run_cycle()
                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    self.logger.error(f"周期执行异常: {e}", exc_info=True)

                time.sleep(self.config.monitor_interval)

        except KeyboardInterrupt:
            self.logger.info("\n收到停止信号，正在关闭...")
            self.shutdown()

    def shutdown(self):
        """关闭机器人"""
        self.logger.info("=" * 60)
        self.logger.info("高级交易机器人停止")

        # 导出监控数据
        self.monitor.export_metrics('monitoring_report.json')

        self.logger.info("=" * 60)
        self.notifier.send_text("🛑 高级交易机器人已停止")


def main():
    """主函数"""
    print("""
    ╔══════════════════════════════════════════════════════════╗
    ║         OKX 高级自动交易机器人 - v2.0                    ║
    ║                                                          ║
    ║  🚀 新增功能:                                            ║
    ║  ✓ 机器学习价格预测                                      ║
    ║  ✓ 智能订单执行 (TWAP/VWAP)                             ║
    ║  ✓ 高级止损/止盈机制                                     ║
    ║  ✓ 实时性能监控和预警                                    ║
    ║  ✓ 动态仓位管理                                          ║
    ╚══════════════════════════════════════════════════════════╝
    """)

    try:
        bot = AdvancedTradingBot(config_path="config.json")
        bot.run()
    except Exception as e:
        print(f"\n❌ 启动失败: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
