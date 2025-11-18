import time
import json
import logging
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from logging.handlers import TimedRotatingFileHandler
from typing import Dict, List, Optional
import okx.Trade_api as TradeAPI
import okx.Public_api as PublicAPI
import okx.Market_api as MarketAPI
import okx.Account_api as AccountAPI
import pandas as pd

# 常量定义
DEFAULT_MONITOR_INTERVAL = 60
DEFAULT_LEVERAGE = 10
DEFAULT_BATCH_SIZE = 5
DEFAULT_ATR_PERIOD = 60
DEFAULT_AMPLITUDE_PERIOD = 60
DEFAULT_KLINE_LIMIT = 241
DEFAULT_EMA_PERIOD = 240
DEFAULT_AMOUNT_USDT = 20
DEFAULT_VALUE_MULTIPLIER = 2
MAX_RETRIES = 3
RETRY_DELAY = 2  # 秒

# 读取配置文件
def load_config(config_path='config.json'):
    """加载并验证配置文件"""
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)

        # 验证必需字段
        if 'okx' not in config:
            raise ValueError("配置文件缺少 'okx' 字段")

        okx_config = config['okx']
        required_fields = ['apiKey', 'secret', 'password']
        for field in required_fields:
            if field not in okx_config or not okx_config[field]:
                raise ValueError(f"OKX配置缺少必需字段: {field}")

        return config
    except FileNotFoundError:
        raise FileNotFoundError(f"配置文件未找到: {config_path}")
    except json.JSONDecodeError as e:
        raise ValueError(f"配置文件JSON格式错误: {e}")

# 加载配置
config = load_config()

# 提取配置
okx_config = config['okx']
trading_pairs_config = config.get('tradingPairs', {})
monitor_interval = config.get('monitor_interval', DEFAULT_MONITOR_INTERVAL)
feishu_webhook = config.get('feishu_webhook', '')
leverage_value = config.get('leverage', DEFAULT_LEVERAGE)

trade_api = TradeAPI.TradeAPI(okx_config["apiKey"], okx_config["secret"], okx_config["password"], False, '0')
market_api = MarketAPI.MarketAPI(okx_config["apiKey"], okx_config["secret"], okx_config["password"], False, '0')
public_api = PublicAPI.PublicAPI(okx_config["apiKey"], okx_config["secret"], okx_config["password"], False, '0')
account_api = AccountAPI.AccountAPI(okx_config["apiKey"], okx_config["secret"], okx_config["password"], False, '0')

log_file = "log/okx2.log"
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

file_handler = TimedRotatingFileHandler(log_file, when='midnight', interval=1, backupCount=7, encoding='utf-8')
file_handler.suffix = "%Y-%m-%d"
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

instrument_info_dict = {}

def fetch_and_store_all_instruments(instType='SWAP'):
    """获取并存储所有交易工具信息"""
    try:
        logger.info(f"正在获取交易工具信息，类型: {instType}")
        response = public_api.get_instruments(instType=instType)
        if 'data' in response and len(response['data']) > 0:
            instrument_info_dict.clear()
            for instrument in response['data']:
                instId = instrument['instId']
                instrument_info_dict[instId] = instrument
            logger.info(f"成功加载 {len(instrument_info_dict)} 个交易工具")
        else:
            raise ValueError("无法获取交易工具数据或数据为空")
    except Exception as e:
        logger.error(f"获取交易工具信息失败: {e}")
        raise

def send_feishu_notification(message):
    """发送飞书通知，带重试机制"""
    if not feishu_webhook:
        return

    headers = {'Content-Type': 'application/json'}
    data = {"msg_type": "text", "content": {"text": message}}

    for attempt in range(MAX_RETRIES):
        try:
            response = requests.post(feishu_webhook, headers=headers, json=data, timeout=10)
            if response.status_code == 200:
                logger.info("飞书通知发送成功")
                return
            else:
                logger.warning(f"飞书通知发送失败 (尝试 {attempt + 1}/{MAX_RETRIES}): {response.text}")
        except requests.exceptions.RequestException as e:
            logger.warning(f"飞书通知请求异常 (尝试 {attempt + 1}/{MAX_RETRIES}): {e}")

        if attempt < MAX_RETRIES - 1:
            time.sleep(RETRY_DELAY)

    logger.error("飞书通知发送失败，已达最大重试次数")

def get_mark_price(instId):
    """获取交易对的当前市场价格"""
    try:
        response = market_api.get_ticker(instId)
        if 'data' in response and len(response['data']) > 0:
            last_price = response['data'][0]['last']
            return float(last_price)
        else:
            raise ValueError(f"{instId} 无法获取市场价格数据")
    except Exception as e:
        logger.error(f"{instId} 获取价格失败: {e}")
        raise

def round_price_to_tick(price, tick_size):
    """
    将价格调整为tick_size的整数倍

    Args:
        price: 原始价格
        tick_size: 最小价格变动单位

    Returns:
        调整后的价格字符串
    """
    # 计算 tick_size 的小数位数
    tick_decimals = len(f"{tick_size:.10f}".rstrip('0').split('.')[1]) if '.' in f"{tick_size:.10f}" else 0

    # 调整价格为 tick_size 的整数倍
    adjusted_price = round(price / tick_size) * tick_size
    return f"{adjusted_price:.{tick_decimals}f}"

def get_historical_klines(instId, bar='1m', limit=DEFAULT_KLINE_LIMIT):
    """
    获取历史K线数据

    Args:
        instId: 交易对ID
        bar: K线周期，如'1m', '5m', '1H'等
        limit: 获取K线数量

    Returns:
        K线数据列表
    """
    try:
        response = market_api.get_candlesticks(instId, bar=bar, limit=limit)
        if 'data' in response and len(response['data']) > 0:
            return response['data']
        else:
            raise ValueError(f"{instId} 无法获取K线数据")
    except Exception as e:
        logger.error(f"{instId} 获取K线数据失败: {e}")
        raise

def calculate_atr(klines, period=DEFAULT_ATR_PERIOD):
    """
    计算平均真实波幅（ATR）

    Args:
        klines: K线数据列表
        period: 计算周期

    Returns:
        ATR值
    """
    if len(klines) < period + 1:
        logger.warning(f"K线数据不足，需要至少 {period + 1} 根K线")
        return 0

    trs = []
    for i in range(1, len(klines)):
        high = float(klines[i][2])
        low = float(klines[i][3])
        prev_close = float(klines[i-1][4])
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)

    if len(trs) >= period:
        atr = sum(trs[-period:]) / period
        return atr
    else:
        return sum(trs) / len(trs) if trs else 0

def calculate_ema_pandas(data, period):
    """
    使用 pandas 计算指数移动平均线（EMA）

    Args:
        data: 收盘价列表
        period: EMA 周期

    Returns:
        EMA 值
    """
    if len(data) < period:
        logger.warning(f"数据不足，需要至少 {period} 个数据点计算EMA")
        return data[-1] if data else 0

    df = pd.Series(data)
    ema = df.ewm(span=period, adjust=False).mean()
    return ema.iloc[-1]  # 返回最后一个 EMA 值


def calculate_average_amplitude(klines, period=DEFAULT_AMPLITUDE_PERIOD):
    """
    计算平均振幅

    Args:
        klines: K线数据列表
        period: 计算周期

    Returns:
        平均振幅百分比
    """
    if len(klines) < period:
        logger.warning(f"K线数据不足，需要至少 {period} 根K线")
        period = len(klines)

    amplitudes = []
    for i in range(len(klines) - period, len(klines)):
        high = float(klines[i][2])
        low = float(klines[i][3])
        close = float(klines[i][4])
        if close > 0:  # 防止除零错误
            amplitude = ((high - low) / close) * 100
            amplitudes.append(amplitude)

    return sum(amplitudes) / len(amplitudes) if amplitudes else 0

def cancel_all_orders(instId):
    """取消指定交易对的所有挂单，支持批量操作"""
    try:
        open_orders = trade_api.get_order_list(instId=instId, state='live')

        # 检查API响应
        if 'code' in open_orders and open_orders['code'] != '0':
            logger.warning(f"{instId} 获取挂单列表失败: {open_orders.get('msg', 'Unknown error')}")
            return

        if 'data' not in open_orders or not open_orders['data']:
            logger.debug(f"{instId} 没有需要取消的挂单")
            return

        order_ids = [order['ordId'] for order in open_orders['data']]

        if not order_ids:
            return

        # 批量取消订单（OKX支持一次取消最多20个订单）
        batch_size = 20
        for i in range(0, len(order_ids), batch_size):
            batch_ids = order_ids[i:i + batch_size]
            cancel_params = [{'instId': instId, 'ordId': ord_id} for ord_id in batch_ids]

            try:
                result = trade_api.cancel_multiple_orders(cancel_params)
                if result.get('code') == '0':
                    logger.info(f"{instId} 成功取消 {len(batch_ids)} 个挂单")
                else:
                    logger.warning(f"{instId} 批量取消订单部分失败: {result.get('msg')}")
            except Exception as e:
                # 如果批量取消失败，尝试逐个取消
                logger.warning(f"{instId} 批量取消失败，尝试逐个取消: {e}")
                for ord_id in batch_ids:
                    try:
                        trade_api.cancel_order(instId=instId, ordId=ord_id)
                    except Exception as cancel_error:
                        logger.error(f"{instId} 取消订单 {ord_id} 失败: {cancel_error}")

    except Exception as e:
        logger.error(f"{instId} 取消挂单时发生错误: {e}")

def set_leverage(instId, leverage, mgnMode='isolated', posSide=None):
    try:
        body = {
            "instId": instId,
            "lever": str(leverage),
            "mgnMode": mgnMode
        }
        if mgnMode == 'isolated' and posSide:
            body["posSide"] = posSide
        response = account_api.set_leverage(**body)
        if response['code'] == '0':
            logger.info(f"Leverage set to {leverage}x for {instId} with mgnMode: {mgnMode}")
        else:
            logger.error(f"Failed to set leverage: {response['msg']}")
    except Exception as e:
        logger.error(f"Error setting leverage: {e}")

def place_order(instId, price, amount_usdt, side):
    if instId not in instrument_info_dict:
        logger.error(f"Instrument {instId} not found in instrument info dictionary")
        return
    tick_size = float(instrument_info_dict[instId]['tickSz'])
    adjusted_price = round_price_to_tick(price, tick_size)

    response = public_api.convert_contract_coin(type='1', instId=instId, sz=str(amount_usdt), px=str(adjusted_price), unit='usdt', opType='open')
    if response['code'] == '0':
        sz = response['data'][0]['sz']
        if float(sz) > 0:

            pos_side = 'long' if side == 'buy' else 'short'
            set_leverage(instId, leverage_value, mgnMode='isolated', posSide=pos_side)
            order_result = trade_api.place_order(
                instId=instId,
                tdMode='isolated',
                posSide=pos_side,
                side=side,
                ordType='limit',
                sz=sz,
                px=str(adjusted_price)
            )
            logger.info(f"Order placed: {order_result}")
        else:
            logger.info(f"{instId}计算出的合约张数太小，无法下单。")
    else:
        logger.info(f"{instId}转换失败: {response['msg']}")
        send_feishu_notification(f"{instId}转换失败: {response['msg']}")

def process_pair(instId, pair_config):
    """
    处理单个交易对的策略逻辑

    Args:
        instId: 交易对ID
        pair_config: 该交易对的配置参数
    """
    try:
        # 获取当前市场价格
        mark_price = get_mark_price(instId)

        # 获取历史K线数据
        klines = get_historical_klines(instId)

        # 提取收盘价数据用于计算 EMA（顺序要新的在最后）
        close_prices = [float(kline[4]) for kline in klines[::-1]]

        # 计算 EMA 并判断趋势
        ema_value = pair_config.get('ema', DEFAULT_EMA_PERIOD)

        # 如果ema值为0，不区分方向，两头都挂单
        if ema_value == 0:
            is_bullish_trend = True
            is_bearish_trend = True
            logger.info(f"{instId} EMA设置为0，双向挂单模式")
        else:
            ema = calculate_ema_pandas(close_prices, period=ema_value)
            current_price = close_prices[-1]

            # 判断趋势
            is_bullish_trend = current_price > ema  # 收盘价在 EMA 之上
            is_bearish_trend = current_price < ema  # 收盘价在 EMA 之下

            trend_status = "多头" if is_bullish_trend else "空头"
            logger.info(f"{instId} EMA{ema_value}: {ema:.6f}, 当前价格: {mark_price:.6f}, 趋势: {trend_status}")

        # 计算 ATR 和平均振幅
        atr = calculate_atr(klines)
        average_amplitude = calculate_average_amplitude(klines)

        # 防止除零错误
        if atr <= 0:
            logger.warning(f"{instId} ATR值异常，跳过本次处理")
            return

        price_atr_ratio = (mark_price / atr) / 100

        logger.info(f"{instId} ATR: {atr:.6f}, 价格/ATR比值: {price_atr_ratio:.3f}, 平均振幅: {average_amplitude:.2f}%")

        # 计算挂单距离
        value_multiplier = pair_config.get('value_multiplier', DEFAULT_VALUE_MULTIPLIER)
        selected_value = (average_amplitude + price_atr_ratio) / 2 * value_multiplier

        long_price_factor = 1 - selected_value / 100
        short_price_factor = 1 + selected_value / 100

        # 获取交易金额
        long_amount_usdt = pair_config.get('long_amount_usdt', DEFAULT_AMOUNT_USDT)
        short_amount_usdt = pair_config.get('short_amount_usdt', DEFAULT_AMOUNT_USDT)

        # 计算目标价格
        target_price_long = mark_price * long_price_factor
        target_price_short = mark_price * short_price_factor

        logger.info(f"{instId} 做多目标价: {target_price_long:.6f} ({-selected_value:.2f}%), 做空目标价: {target_price_short:.6f} (+{selected_value:.2f}%)")

        # 先取消所有挂单
        cancel_all_orders(instId)

        # 根据趋势判断挂单
        if is_bullish_trend and long_amount_usdt > 0:
            logger.info(f"{instId} 多头趋势，挂多单")
            place_order(instId, target_price_long, long_amount_usdt, 'buy')
        elif not is_bullish_trend:
            logger.debug(f"{instId} 非多头趋势，跳过多单")

        if is_bearish_trend and short_amount_usdt > 0:
            logger.info(f"{instId} 空头趋势，挂空单")
            place_order(instId, target_price_short, short_amount_usdt, 'sell')
        elif not is_bearish_trend:
            logger.debug(f"{instId} 非空头趋势，跳过空单")

    except Exception as e:
        error_message = f'{instId} 处理失败: {e}'
        logger.error(error_message, exc_info=True)
        send_feishu_notification(error_message)

def main():
    """主函数，初始化并运行交易策略"""
    logger.info("=" * 60)
    logger.info("交易机器人启动")
    logger.info(f"监控间隔: {monitor_interval}秒")
    logger.info(f"杠杆倍数: {leverage_value}x")
    logger.info("=" * 60)

    try:
        # 初始化：获取所有交易工具信息
        fetch_and_store_all_instruments()

        # 获取配置的交易对列表
        inst_ids = list(trading_pairs_config.keys())

        if not inst_ids:
            logger.error("配置文件中没有交易对，程序退出")
            return

        logger.info(f"已配置 {len(inst_ids)} 个交易对: {', '.join(inst_ids)}")

        batch_size = DEFAULT_BATCH_SIZE  # 每批处理的数量

        # 主循环
        loop_count = 0
        while True:
            loop_count += 1
            logger.info(f"\n{'='*60}")
            logger.info(f"第 {loop_count} 轮处理开始")
            logger.info(f"{'='*60}")

            try:
                # 分批处理交易对，避免并发过多
                for i in range(0, len(inst_ids), batch_size):
                    batch = inst_ids[i:i + batch_size]
                    logger.info(f"处理批次 {i//batch_size + 1}: {', '.join(batch)}")

                    with ThreadPoolExecutor(max_workers=batch_size) as executor:
                        futures = {
                            executor.submit(process_pair, instId, trading_pairs_config[instId]): instId
                            for instId in batch
                        }

                        for future in as_completed(futures):
                            inst_id = futures[future]
                            try:
                                future.result()  # 获取结果，如有异常会抛出
                            except Exception as e:
                                logger.error(f"{inst_id} 处理异常: {e}", exc_info=True)

            except KeyboardInterrupt:
                logger.info("收到终止信号，正在退出...")
                break
            except Exception as e:
                logger.error(f"主循环发生异常: {e}", exc_info=True)
                send_feishu_notification(f"交易机器人主循环异常: {e}")

            logger.info(f"第 {loop_count} 轮处理完成，等待 {monitor_interval} 秒后继续...\n")
            time.sleep(monitor_interval)

    except KeyboardInterrupt:
        logger.info("程序被用户中断")
    except Exception as e:
        logger.error(f"程序启动失败: {e}", exc_info=True)
        send_feishu_notification(f"交易机器人启动失败: {e}")
    finally:
        logger.info("交易机器人已停止")

if __name__ == '__main__':
    main()
