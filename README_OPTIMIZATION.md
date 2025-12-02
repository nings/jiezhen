# 项目优化说明 - 2025年12月更新

## 🎯 核心改进

本次优化主要解决了以下问题：
1. ✅ **无需 API 密钥即可测试** - 支持 dry_run 模式
2. ✅ **配置更安全** - 区分开发和生产环境
3. ✅ **更灵活的交易对管理** - 支持独立启用/禁用
4. ✅ **更好的日志输出** - 清晰标记模拟操作

---

## 📋 快速使用指南

### 方式 1：模拟运行（推荐新手）

**无需填写 API 密钥，安全测试策略**

1. **确认配置文件** (`config.json`)：
```json
{
  "mode": "dry_run",
  "dry_run": true,
  "okx": {
    "apiKey": "",
    "secret": "",
    "password": ""
  }
}
```

2. **运行程序**：
```bash
uv run zhen_2.py
```

3. **查看输出**：
```
✓ 配置加载成功 [模式: dry_run，模拟运行，不会真实下单]
============================================================
交易机器人启动
运行模式: DRY_RUN
监控间隔: 60秒
杠杆倍数: 10x
批处理大小: 5
⚠️  DRY_RUN 模式：不会真实下单和撤单
============================================================
```

4. **观察模拟交易**：
```
[DRY_RUN] 跳过取消挂单: PNUT-USDT-SWAP
[DRY_RUN] 模拟下单: PNUT-USDT-SWAP | 方向=short | 价格=0.09120 | 金额=20 USDT | 杠杆=10x
```

### 方式 2：实盘运行（谨慎使用）

**⚠️ 警告：实盘会真实下单，请确保充分测试后再使用**

1. **修改配置文件**：
```json
{
  "mode": "live",
  "dry_run": false,
  "okx": {
    "apiKey": "your-real-api-key",
    "secret": "your-real-secret",
    "password": "your-real-password"
  }
}
```

2. **运行程序**：
```bash
uv run zhen_2.py
```

3. **确认实盘模式**：
```
✓ 配置加载成功 [模式: live]
============================================================
交易机器人启动
运行模式: LIVE
监控间隔: 60秒
杠杆倍数: 10x
批处理大小: 5
============================================================
```

---

## 🔧 新增配置项说明

### 1. 运行模式配置

```json
{
  "mode": "dry_run",        // 运行模式：dry_run 或 live
  "dry_run": true           // 冗余开关，建议与 mode 保持一致
}
```

| 模式 | 说明 | API 密钥要求 | 下单行为 |
|------|------|-------------|---------|
| `dry_run` | 模拟运行 | 可以为空 | 仅打印日志，不真实下单 |
| `live` | 实盘运行 | 必须填写 | 真实下单到交易所 |

### 2. 批处理配置

```json
{
  "batch_size": 5           // 每批并发处理的交易对数量
}
```

- **较小值 (3-5)**：适合网络不稳定或交易对较少的情况
- **较大值 (8-10)**：适合稳定网络和多交易对场景

### 3. 风控参数（预留）

```json
{
  "risk": {
    "max_position_usdt_per_pair": 500,    // 单交易对最大仓位（USDT）
    "max_orders_per_day": 100,            // 每日最大开仓次数
    "max_daily_loss_usdt": 1000           // 每日最大亏损（USDT）
  }
}
```

**注意**：这些参数已在配置中预留，但代码中尚未实现具体逻辑。后续版本会添加。

### 4. 交易对启用开关

```json
{
  "tradingPairs": {
    "BTC-USDT-SWAP": {
      "enabled": true,              // 新增：是否启用此交易对
      "long_amount_usdt": 50,
      "short_amount_usdt": 50,
      "value_multiplier": 2,
      "ema": 240
    },
    "ETH-USDT-SWAP": {
      "enabled": false,             // 禁用此交易对
      "long_amount_usdt": 30,
      "short_amount_usdt": 30,
      "value_multiplier": 2,
      "ema": 240
    }
  }
}
```

**好处**：
- 无需删除配置即可临时禁用某些交易对
- 方便进行 A/B 测试
- 快速调整交易策略范围

---

## 📊 完整配置示例

### 示例 1：保守型配置（模拟运行）

```json
{
  "mode": "dry_run",
  "dry_run": true,
  "binance": {},
  "okx": {
    "apiKey": "",
    "secret": "",
    "password": "",
    "leverage": 1.0
  },
  "bitget": {},
  "feishu_webhook": "https://open.feishu.cn/open-apis/bot/v2/hook/your-webhook",
  "monitor_interval": 60,
  "batch_size": 3,
  "leverage": 5,
  "risk": {
    "max_position_usdt_per_pair": 200,
    "max_orders_per_day": 50,
    "max_daily_loss_usdt": 500
  },
  "tradingPairs": {
    "BTC-USDT-SWAP": {
      "long_amount_usdt": 20,
      "short_amount_usdt": 20,
      "value_multiplier": 2.5,
      "ema": 240,
      "enabled": true
    },
    "ETH-USDT-SWAP": {
      "long_amount_usdt": 15,
      "short_amount_usdt": 15,
      "value_multiplier": 2.5,
      "ema": 240,
      "enabled": true
    }
  }
}
```

### 示例 2：激进型配置（实盘运行）

```json
{
  "mode": "live",
  "dry_run": false,
  "binance": {},
  "okx": {
    "apiKey": "your-api-key",
    "secret": "your-secret",
    "password": "your-password",
    "leverage": 1.0
  },
  "bitget": {},
  "feishu_webhook": "https://open.feishu.cn/open-apis/bot/v2/hook/your-webhook",
  "monitor_interval": 30,
  "batch_size": 8,
  "leverage": 15,
  "risk": {
    "max_position_usdt_per_pair": 1000,
    "max_orders_per_day": 200,
    "max_daily_loss_usdt": 2000
  },
  "tradingPairs": {
    "BTC-USDT-SWAP": {
      "long_amount_usdt": 100,
      "short_amount_usdt": 100,
      "value_multiplier": 1.8,
      "ema": 240,
      "enabled": true
    },
    "ETH-USDT-SWAP": {
      "long_amount_usdt": 80,
      "short_amount_usdt": 80,
      "value_multiplier": 1.8,
      "ema": 240,
      "enabled": true
    },
    "SOL-USDT-SWAP": {
      "long_amount_usdt": 50,
      "short_amount_usdt": 50,
      "value_multiplier": 2.0,
      "ema": 240,
      "enabled": true
    }
  }
}
```

---

## 🔍 代码改进详情

### 1. `load_config()` 函数优化

**改进前**：
```python
# 无论什么模式都强制要求 API 密钥
for field in required_fields:
    if field not in okx_config or not okx_config[field]:
        raise ValueError(f"OKX配置缺少必需字段: {field}")
```

**改进后**：
```python
# 获取运行模式
mode = config.get('mode', 'dry_run')
if mode not in ('live', 'dry_run'):
    raise ValueError(f"不支持的运行模式: {mode}")

# 只在 live 模式下强制校验 OKX 密钥
if mode == 'live':
    for field in required_fields:
        if field not in okx_config or not okx_config[field]:
            raise ValueError(f"live 模式下 OKX 配置缺少必需字段: {field}")
    print(f"✓ 配置加载成功 [模式: {mode}]")
else:
    print(f"✓ 配置加载成功 [模式: {mode}，模拟运行，不会真实下单]")
```

### 2. 下单函数增加保护

**改进的函数**：
- `place_order()` - 下单
- `cancel_all_orders()` - 撤单
- `set_leverage()` - 设置杠杆

**示例**：
```python
def place_order(instId, price, amount_usdt, side):
    if instId not in instrument_info_dict:
        logger.error(f"Instrument {instId} not found")
        return
    
    tick_size = float(instrument_info_dict[instId]['tickSz'])
    adjusted_price = round_price_to_tick(price, tick_size)
    pos_side = 'long' if side == 'buy' else 'short'
    
    # 新增：dry_run 保护
    if dry_run:
        logger.info(f"[DRY_RUN] 模拟下单: {instId} | 方向={pos_side} | 价格={adjusted_price} | 金额={amount_usdt} USDT | 杠杆={leverage_value}x")
        return
    
    # 原有的真实下单逻辑...
```

### 3. 交易对过滤优化

**改进前**：
```python
inst_ids = list(trading_pairs_config.keys())
```

**改进后**：
```python
# 只处理启用的交易对
inst_ids = [instId for instId, config in trading_pairs_config.items() 
            if config.get('enabled', True)]
```

### 4. 启动日志增强

**改进后的输出**：
```python
logger.info("="*60)
logger.info("交易机器人启动")
logger.info(f"运行模式: {mode.upper()}")
logger.info(f"监控间隔: {monitor_interval}秒")
logger.info(f"杠杆倍数: {leverage_value}x")
logger.info(f"批处理大小: {batch_size}")
if dry_run:
    logger.warning("⚠️  DRY_RUN 模式：不会真实下单和撤单")
logger.info("="*60)
```

---

## 🚀 从旧版本迁移

### 步骤 1：备份现有配置
```bash
cp config.json config.json.backup
```

### 步骤 2：更新配置文件

在 `config.json` 顶部添加：
```json
{
  "mode": "dry_run",
  "dry_run": true,
  "batch_size": 5,
  "risk": {
    "max_position_usdt_per_pair": 500,
    "max_orders_per_day": 100,
    "max_daily_loss_usdt": 1000
  },
  // ... 其他原有配置
}
```

在每个交易对配置中添加：
```json
"BTC-USDT-SWAP": {
  "enabled": true,
  // ... 其他原有配置
}
```

### 步骤 3：使用新版本运行

```bash
# 先在 dry_run 模式测试
uv run zhen_2.py

# 确认无误后，再切换到 live 模式
```

---

## ⚠️ 重要提醒

### 安全检查清单

在切换到 `live` 模式前，请确认：

- [ ] 已在 `dry_run` 模式下充分测试（至少运行 24 小时）
- [ ] 理解所有配置参数的含义
- [ ] 设置了合理的仓位大小（建议从小金额开始）
- [ ] OKX API 密钥权限正确（只开启交易权限，禁用提现）
- [ ] 设置了 IP 白名单（在 OKX 后台）
- [ ] 配置了飞书通知（及时接收异常告警）
- [ ] 准备了紧急停止方案（Ctrl+C 或 `pkill -f zhen_2.py`）

### 常见错误处理

**错误 1**：`ValueError: live 模式下 OKX 配置缺少必需字段: apiKey`
- **原因**：在 `live` 模式下 API 密钥为空
- **解决**：填写真实的 API 密钥，或切换到 `dry_run` 模式

**错误 2**：程序运行但没有任何下单日志
- **原因**：可能所有交易对都被禁用了
- **解决**：检查 `enabled` 字段，确保至少有一个交易对为 `true`

**错误 3**：`不支持的运行模式: xxx`
- **原因**：`mode` 字段值不正确
- **解决**：只能使用 `"live"` 或 `"dry_run"`

---

## 📚 相关文档

- **OPTIMIZATION_SUMMARY.md** - 详细的优化总结和后续规划
- **QUICK_START.md** - 快速开始指南
- **config.json** - 配置文件示例

---

## 🎓 最佳实践

### 开发流程建议

1. **本地测试**（dry_run 模式）
   - 调整策略参数
   - 观察信号质量
   - 验证逻辑正确性

2. **小资金实盘**（live 模式 + 小仓位）
   - 每个交易对 10-20 USDT
   - 运行 1-2 周
   - 收集真实数据

3. **逐步放大**（根据表现调整）
   - 分析收益率和胜率
   - 优化参数配置
   - 逐步增加仓位

### 参数调优技巧

**保守 → 激进的调整路径**：

| 阶段 | leverage | amount_usdt | value_multiplier | monitor_interval |
|------|----------|-------------|------------------|------------------|
| 测试 | 3-5 | 10-20 | 2.5-3.0 | 60 |
| 初期 | 5-8 | 20-50 | 2.0-2.5 | 60 |
| 成熟 | 10-15 | 50-100 | 1.8-2.0 | 30-60 |
| 激进 | 15-20 | 100+ | 1.5-1.8 | 20-30 |

---

**祝交易顺利！如有问题，请查看日志文件或联系技术支持。** 🚀
