# Jiezhen 接针策略 - 模块化版本

## 项目简介

这是一个模块化重构后的加密货币"接针"策略交易机器人，使用OKX交易所API。

策略原理：使用EMA判断短期趋势，在下方挂单接住插下来的针（wick）。

## 模块化结构

```
jiezhen/
├── src/                          # 源代码目录
│   ├── config/                   # 配置管理模块
│   │   ├── __init__.py
│   │   └── config_loader.py      # 配置文件加载器
│   ├── core/                     # 核心模块
│   │   ├── __init__.py
│   │   ├── api_client.py         # OKX API客户端封装
│   │   └── instrument_manager.py # 交易品种管理器
│   ├── indicators/               # 技术指标模块
│   │   ├── __init__.py
│   │   ├── atr.py                # ATR (平均真实波幅) 计算
│   │   ├── ema.py                # EMA (指数移动平均) 计算
│   │   └── amplitude.py          # 振幅计算
│   ├── strategies/               # 策略模块
│   │   ├── __init__.py
│   │   ├── base_strategy.py      # 策略基类
│   │   ├── zhen_strategy.py      # Zhen策略 (使用最小值方法)
│   │   └── zhen2_strategy.py     # Zhen2策略 (使用平均值方法)
│   ├── trading/                  # 交易管理模块
│   │   ├── __init__.py
│   │   ├── order_manager.py      # 订单管理器
│   │   └── position_manager.py   # 持仓管理器
│   └── utils/                    # 工具模块
│       ├── __init__.py
│       ├── logger.py             # 日志管理
│       ├── notification.py       # 通知管理（飞书）
│       └── price_utils.py        # 价格工具函数
├── okx/                          # OKX API库
├── main.py                       # 主程序入口（版本1）
├── main_v2.py                    # 主程序入口（版本2）
├── zhen.py                       # 原版脚本（保留）
├── zhen_2.py                     # 原版脚本（保留）
├── config.json                   # 配置文件
├── requirements.txt              # 依赖包
└── README.md                     # 原始说明文档
```

## 模块说明

### 1. 配置管理模块 (src/config/)

**config_loader.py**: 负责加载和管理配置文件
- 统一的配置加载接口
- 提供便捷的配置访问方法

### 2. 核心模块 (src/core/)

**api_client.py**: OKX API客户端封装
- 封装所有OKX API调用
- 提供统一的接口
- 简化API使用

**instrument_manager.py**: 交易品种管理器
- 管理交易品种信息
- 缓存品种数据
- 提供tick_size等关键信息

### 3. 技术指标模块 (src/indicators/)

**atr.py**: ATR (Average True Range) 计算
- 计算平均真实波幅

**ema.py**: EMA (Exponential Moving Average) 计算
- 使用pandas计算指数移动平均

**amplitude.py**: 振幅计算
- 计算K线平均振幅

### 4. 策略模块 (src/strategies/)

**base_strategy.py**: 策略基类
- 定义策略接口
- 实现通用的交易逻辑
- 提供可扩展的框架

**zhen_strategy.py**: Zhen策略（版本1）
- 使用 `min(average_amplitude, price_atr_ratio) * value_multiplier` 计算挂单距离
- 对应原始的 zhen.py

**zhen2_strategy.py**: Zhen2策略（版本2）
- 使用 `(average_amplitude + price_atr_ratio) / 2 * value_multiplier` 计算挂单距离
- 更侧重ATR的影响
- 对应原始的 zhen_2.py

### 5. 交易管理模块 (src/trading/)

**order_manager.py**: 订单管理器
- 下单、撤单
- 杠杆设置
- 订单查询

**position_manager.py**: 持仓管理器
- 持仓查询
- 持仓管理

### 6. 工具模块 (src/utils/)

**logger.py**: 日志管理
- 统一的日志记录
- 按天轮转
- 文件和控制台双输出

**notification.py**: 通知管理
- 飞书通知
- 错误通知
- 订单通知

**price_utils.py**: 价格工具函数
- 价格调整为tick_size的整数倍

## 使用方法

### 1. 配置文件

将 `config_bak.json` 复制为 `config.json`，并填写你的OKX API信息：

```json
{
    "okx": {
        "apiKey": "your_api_key",
        "secret": "your_secret",
        "password": "your_password"
    },
    "feishu_webhook": "your_feishu_webhook_url",
    "monitor_interval": 60,
    "leverage": 10,
    "tradingPairs": {
        "BTC-USDT-SWAP": {
            "long_amount_usdt": 20,
            "short_amount_usdt": 20,
            "value_multiplier": 3,
            "ema": 240
        }
    }
}
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 运行程序

**运行版本1（使用最小值方法）:**
```bash
python main.py
```

**运行版本2（使用平均值方法，更侧重ATR）:**
```bash
python main_v2.py
```

**或者运行原始版本（未模块化）:**
```bash
python zhen.py    # 版本1
python zhen_2.py  # 版本2
```

## 两个策略版本的区别

参考: https://x.com/huojichuanqi/status/1858991226877603902

**版本1 (main.py / zhen.py)**:
- 挂单距离 = `min(平均振幅, 价格/ATR比值) × 价值乘数`
- 取较小值，更保守

**版本2 (main_v2.py / zhen_2.py)**:
- 挂单距离 = `(平均振幅 + 价格/ATR比值) / 2 × 价值乘数`
- 取平均值，更侧重ATR

## 模块化优势

1. **代码复用**: 将公共逻辑抽取到基类和工具模块
2. **易于维护**: 每个模块职责单一，便于定位和修改
3. **可扩展性**: 可以轻松添加新的策略、指标和功能
4. **可测试性**: 模块化后便于单元测试
5. **代码清晰**: 结构清晰，易于理解和协作

## 配置参数说明

### 全局参数
- `apiKey`: OKX API 的公钥
- `secret`: OKX API 的私钥
- `password`: OKX 的交易密码
- `leverage`: 默认杠杆倍数
- `feishu_webhook`: 飞书通知地址
- `monitor_interval`: 循环间隔周期（秒）

### 交易对参数
- `long_amount_usdt`: 做多时每笔订单的资金量（USDT）
- `short_amount_usdt`: 做空时每笔订单的资金量（USDT）
- `value_multiplier`: 价值乘数，调整风险/回报比
- `ema`: EMA周期，用于判断趋势（0表示不区分方向，两头都挂单）

## 注意事项

1. 环境要求：Python 3.9+
2. 交易模式：开平仓模式，不支持单向持仓
3. 如果跑15m周期以上，建议用1h的EMA判断多空，或人工介入判断
4. 请在测试环境充分测试后再使用实盘

## 视频说明

https://www.youtube.com/watch?v=b-LhdQomOxk

## 打赏地址

TRC20: TUunBuqQ1ZDYt9WrA3ZarndFPQgefXqZAM
