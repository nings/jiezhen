"""
主程序 - 重构版本
工程化改进：模块化设计、错误处理、风险控制、性能优化
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


class TradingBot:
    """交易机器人主类"""

    def __init__(self, config_path: str = "config.json"):
        """
        初始化交易机器人

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
            name='trading_bot',
            log_file='log/trading_bot.log',
            level=logging.INFO
        )
        self.logger.info("=" * 60)
        self.logger.info("交易机器人启动")
        self.logger.info("=" * 60)

        # 初始化飞书通知
        self.notifier = FeishuNotifier(
            webhook_url=self.config.feishu_webhook,
            enabled=bool(self.config.feishu_webhook)
        )

        # 初始化OKX API
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

        # 获取合约信息
        self.instrument_info: Dict[str, Dict] = {}
        self._fetch_instrument_info()

        # 初始化技术指标计算器
        self.indicator_calculator = TechnicalIndicators(
            cache_ttl=self.config.cache_ttl
        )

        # 初始化策略
        self.strategy = StrategyFactory.create_strategy(
            strategy_type='pinbar',  # 使用接针策略
            indicator_calculator=self.indicator_calculator
        )
        self.logger.info("✓ 策略初始化完成：接针策略（PinBar）")

        # 初始化订单管理器
        self.order_manager = OrderManager(
            trade_api=self.trade_api,
            market_api=self.market_api,
            public_api=self.public_api,
            account_api=self.account_api,
            instrument_info=self.instrument_info,
            retry_config=RetryConfig(max_retries=3)
        )

        # 初始化风险管理器
        self.risk_manager = RiskManager(
            max_position_size_usdt=self.config.risk.max_position_size_usdt,
            max_total_position_usdt=self.config.risk.max_total_position_usdt,
            max_daily_loss_usdt=self.config.risk.max_daily_loss_usdt,
            max_orders_per_pair=self.config.risk.max_orders_per_pair,
            enable_risk_control=self.config.risk.enable_risk_control
        )
        self.logger.info(f"✓ 风险控制已{'启用' if self.config.risk.enable_risk_control else '禁用'}")

        # 统计信息
        self.processed_count = 0
        self.error_count = 0

        self.logger.info("=" * 60)
        self.logger.info(f"已配置交易对: {len(self.config.trading_pairs)}")
        for inst_id in self.config.get_all_inst_ids():
            self.logger.info(f"  - {inst_id}")
        self.logger.info("=" * 60)

    def _fetch_instrument_info(self):
        """获取并缓存所有合约信息"""
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
                raise ValueError("获取合约信息失败或响应格式错误")

        except Exception as e:
            self.logger.error(f"❌ 获取合约信息失败: {e}")
            self.notifier.notify_error(f"获取合约信息失败: {e}")
            raise

    def process_trading_pair(self, inst_id: str) -> bool:
        """
        处理单个交易对

        Args:
            inst_id: 交易对ID

        Returns:
            是否处理成功
        """
        try:
            # 获取配置
            pair_config = self.config.get_pair_config(inst_id)
            if not pair_config:
                self.logger.error(f"{inst_id}: 配置未找到")
                return False

            # 检查是否应该停止交易
            should_stop, reason = self.risk_manager.should_stop_trading()
            if should_stop:
                self.logger.warning(f"风险控制: {reason} - 停止交易")
                self.notifier.notify_risk_alert(reason, level='critical')
                return False

            self.logger.info(f"\n{'='*60}")
            self.logger.info(f"处理交易对: {inst_id}")
            self.logger.info(f"{'='*60}")

            # 获取当前价格
            current_price = self.order_manager.get_mark_price(inst_id)
            self.logger.info(f"{inst_id}: 当前价格 = {current_price:.6f}")

            # 获取K线数据
            klines = self.order_manager.get_historical_klines(inst_id)
            self.logger.info(f"{inst_id}: 获取了 {len(klines)} 根K线")

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

            # 撤销所有未成交订单
            cancelled_count = self.order_manager.cancel_all_orders(inst_id)
            self.risk_manager.clear_orders(inst_id)

            # 根据信号下单
            orders_placed = 0

            # 做多单
            if signal.should_long:
                can_order, reason = self.risk_manager.can_place_order(
                    inst_id=inst_id,
                    amount_usdt=pair_config.long_amount_usdt,
                    side='buy'
                )

                if can_order:
                    self.logger.info(f"{inst_id}: 当前为多头趋势，挂多单")
                    result = self.order_manager.place_limit_order(
                        inst_id=inst_id,
                        side='buy',
                        price=signal.long_price,
                        amount_usdt=pair_config.long_amount_usdt,
                        leverage=self.config.leverage
                    )
                    if result:
                        self.risk_manager.record_order(inst_id)
                        orders_placed += 1
                else:
                    self.logger.warning(f"{inst_id}: 风险控制阻止做多 - {reason}")
            else:
                self.logger.info(f"{inst_id}: 当前非多头趋势，跳过多单")

            # 做空单
            if signal.should_short:
                can_order, reason = self.risk_manager.can_place_order(
                    inst_id=inst_id,
                    amount_usdt=pair_config.short_amount_usdt,
                    side='sell'
                )

                if can_order:
                    self.logger.info(f"{inst_id}: 当前为空头趋势，挂空单")
                    result = self.order_manager.place_limit_order(
                        inst_id=inst_id,
                        side='sell',
                        price=signal.short_price,
                        amount_usdt=pair_config.short_amount_usdt,
                        leverage=self.config.leverage
                    )
                    if result:
                        self.risk_manager.record_order(inst_id)
                        orders_placed += 1
                else:
                    self.logger.warning(f"{inst_id}: 风险控制阻止做空 - {reason}")
            else:
                self.logger.info(f"{inst_id}: 当前非空头趋势，跳过空单")

            self.logger.info(
                f"{inst_id}: 处理完成 (撤销: {cancelled_count}, 下单: {orders_placed})"
            )
            return True

        except Exception as e:
            error_msg = f"{inst_id}: 处理异常 - {e}"
            self.logger.error(error_msg, exc_info=True)
            self.notifier.notify_error(str(e), inst_id)
            self.error_count += 1
            return False

    def run_cycle(self):
        """运行一个完整的交易周期"""
        start_time = time.time()
        inst_ids = self.config.get_all_inst_ids()
        total = len(inst_ids)

        self.logger.info(f"\n{'#'*60}")
        self.logger.info(f"开始新的交易周期 (共 {total} 个交易对)")
        self.logger.info(f"{'#'*60}")

        # 显示风险指标
        risk_metrics = self.risk_manager.get_risk_metrics()
        self.logger.info(f"风险指标: {risk_metrics}")

        success_count = 0
        batch_size = self.config.batch_size

        # 批量并发处理
        for i in range(0, total, batch_size):
            batch = inst_ids[i:i + batch_size]
            self.logger.info(f"\n处理批次 {i//batch_size + 1} ({len(batch)} 个交易对)")

            with ThreadPoolExecutor(max_workers=batch_size) as executor:
                futures = {
                    executor.submit(self.process_trading_pair, inst_id): inst_id
                    for inst_id in batch
                }

                for future in as_completed(futures):
                    inst_id = futures[future]
                    try:
                        if future.result():
                            success_count += 1
                            self.processed_count += 1
                    except Exception as e:
                        self.logger.error(f"{inst_id}: 处理失败 - {e}")

        elapsed = time.time() - start_time
        self.logger.info(f"\n{'#'*60}")
        self.logger.info(
            f"周期完成: 成功 {success_count}/{total}, "
            f"耗时 {elapsed:.2f}秒"
        )
        self.logger.info(f"{'#'*60}\n")

        # 检查风险等级
        risk_level = self.risk_manager.get_risk_level()
        if risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
            alert_msg = (
                f"当前风险等级: {risk_level.value}\n"
                f"{self.risk_manager.get_risk_metrics()}"
            )
            self.notifier.notify_risk_alert(alert_msg, level=risk_level.value)

    def run(self):
        """运行交易机器人"""
        self.logger.info("交易机器人开始运行...")
        self.notifier.send_text("🤖 交易机器人已启动")

        try:
            while True:
                try:
                    self.run_cycle()
                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    self.logger.error(f"周期执行异常: {e}", exc_info=True)
                    self.notifier.notify_error(f"周期执行异常: {e}")

                # 等待下一个周期
                self.logger.info(
                    f"等待 {self.config.monitor_interval} 秒后开始下一个周期...\n"
                )
                time.sleep(self.config.monitor_interval)

        except KeyboardInterrupt:
            self.logger.info("\n收到停止信号，正在关闭...")
            self.shutdown()
        except Exception as e:
            self.logger.critical(f"致命错误: {e}", exc_info=True)
            self.notifier.notify_error(f"机器人崩溃: {e}")
            self.shutdown()
            raise

    def shutdown(self):
        """关闭机器人"""
        self.logger.info("=" * 60)
        self.logger.info("交易机器人停止")
        self.logger.info(f"总处理次数: {self.processed_count}")
        self.logger.info(f"错误次数: {self.error_count}")

        # 显示缓存统计
        cache_stats = self.indicator_calculator.get_cache_stats()
        self.logger.info(f"缓存统计: {cache_stats}")

        # 显示风险报告
        if self.config.risk.enable_risk_control:
            self.logger.info("\n" + self.risk_manager.get_position_report())

        self.logger.info("=" * 60)
        self.notifier.send_text("🛑 交易机器人已停止")


def main():
    """主函数"""
    print("""
    ╔══════════════════════════════════════════════════════════╗
    ║           OKX 自动交易机器人 - 重构版本                  ║
    ║                                                          ║
    ║  工程改进:                                               ║
    ║  ✓ 模块化架构设计                                        ║
    ║  ✓ 类型提示和文档                                        ║
    ║  ✓ 技术指标缓存                                          ║
    ║  ✓ 错误处理和重试                                        ║
    ║  ✓ 配置验证                                              ║
    ║  ✓ 风险控制                                              ║
    ║  ✓ 性能优化                                              ║
    ╚══════════════════════════════════════════════════════════╝
    """)

    try:
        bot = TradingBot(config_path="config.json")
        bot.run()
    except Exception as e:
        print(f"\n❌ 启动失败: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
