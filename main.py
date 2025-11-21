"""
Jiezhen 接针策略 - 主程序入口（版本1）
使用 min(average_amplitude, price_atr_ratio) 计算挂单距离
"""
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from src.config.config_loader import ConfigLoader
from src.core.api_client import OKXClient
from src.core.instrument_manager import InstrumentManager
from src.trading.order_manager import OrderManager
from src.utils.logger import Logger
from src.utils.notification import NotificationManager
from src.strategies.zhen_strategy import ZhenStrategy

# 初始化日志
logger = Logger.get_logger(__name__, log_file="log/okx.log")


def main():
    """主函数"""
    try:
        # 加载配置
        logger.info("=" * 80)
        logger.info("Jiezhen 接针策略 启动 (版本1)")
        logger.info("=" * 80)

        config_loader = ConfigLoader('config.json')
        logger.info("配置文件加载成功")

        # 初始化OKX客户端
        okx_config = config_loader.okx_config
        client = OKXClient(
            api_key=okx_config['apiKey'],
            secret=okx_config['secret'],
            password=okx_config['password'],
            flag='0'
        )
        logger.info("OKX客户端初始化成功")

        # 初始化通知管理器
        notification_manager = NotificationManager(config_loader.feishu_webhook)

        # 初始化交易品种管理器
        instrument_manager = InstrumentManager(client)
        instrument_manager.fetch_all_instruments()
        logger.info("交易品种信息加载成功")

        # 初始化订单管理器
        order_manager = OrderManager(
            client=client,
            instrument_manager=instrument_manager,
            notification_manager=notification_manager,
            leverage=config_loader.leverage
        )
        logger.info("订单管理器初始化成功")

        # 初始化策略
        strategy = ZhenStrategy(
            client=client,
            instrument_manager=instrument_manager,
            order_manager=order_manager,
            notification_manager=notification_manager
        )
        logger.info("策略初始化成功 - ZhenStrategy (使用最小值方法)")

        # 获取交易对列表
        trading_pairs = config_loader.trading_pairs
        inst_ids = list(trading_pairs.keys())
        batch_size = 5  # 每批处理的数量

        logger.info(f"监控交易对: {inst_ids}")
        logger.info(f"监控间隔: {config_loader.monitor_interval}秒")
        logger.info("开始监控...")

        # 主循环
        while True:
            for i in range(0, len(inst_ids), batch_size):
                batch = inst_ids[i:i + batch_size]
                with ThreadPoolExecutor(max_workers=batch_size) as executor:
                    futures = [
                        executor.submit(strategy.process_pair, inst_id, trading_pairs[inst_id])
                        for inst_id in batch
                    ]
                    for future in as_completed(futures):
                        try:
                            future.result()  # Raise any exceptions caught during execution
                        except Exception as e:
                            logger.error(f"处理交易对时发生错误: {e}")

            time.sleep(config_loader.monitor_interval)

    except KeyboardInterrupt:
        logger.info("收到退出信号，程序正在停止...")
    except Exception as e:
        error_msg = f"程序发生严重错误: {e}"
        logger.error(error_msg)
        try:
            notification_manager = NotificationManager(ConfigLoader('config.json').feishu_webhook)
            notification_manager.send_feishu(error_msg)
        except:
            pass
        raise


if __name__ == '__main__':
    main()
