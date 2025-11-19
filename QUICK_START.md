# 快速开始指南

## 项目概览

本项目包含4个交易策略，从简单到复杂，从低频到AI驱动：

| 策略文件 | 类型 | 周期 | 核心技术 | 适用场景 |
|---------|------|------|---------|---------|
| **zhen.py** | 趋势接针（保守） | 60秒 | EMA + ATR (min策略) | 稳定趋势市场 |
| **zhen_2.py** | 趋势接针（平衡） | 60秒 | EMA + ATR (avg策略) | 通用市场 |
| **zhen_orderbook.py** | 订单簿分析（激进） | 5-30秒 | OBI + WAP + Depth | 高流动性品种 |
| **zhen_ml.py** | AI机器学习⭐新增 | 10秒 | LightGBM + 40+特征 | 量化研究/高级用户 |

---

## 策略选择建议

### 1. 初学者/稳健型 → 使用 `zhen.py`

**特点**：
- ✅ 最保守，使用`min(振幅, ATR)`计算挂单距离
- ✅ 60秒周期，不频繁交易
- ✅ 依赖EMA趋势判断，抗噪音能力强

**推荐配置**：
```json
{
  "monitor_interval": 60,
  "leverage": 5,
  "tradingPairs": {
    "BTC-USDT-SWAP": {
      "long_amount_usdt": 20,
      "short_amount_usdt": 20,
      "ema": 240,
      "value_multiplier": 2
    }
  }
}
```

**启动**：
```bash
python zhen.py
```

---

### 2. 平衡型/主力策略 → 使用 `zhen_2.py`

**特点**：
- ✅ 平衡策略，使用`(振幅 + ATR) / 2`
- ✅ 60秒周期
- ✅ 比zhen.py更积极，但仍保守

**推荐配置**：
```json
{
  "monitor_interval": 60,
  "leverage": 10,
  "tradingPairs": {
    "BTC-USDT-SWAP": {
      "long_amount_usdt": 50,
      "short_amount_usdt": 50,
      "ema": 240,
      "value_multiplier": 2
    },
    "ETH-USDT-SWAP": {
      "long_amount_usdt": 30,
      "short_amount_usdt": 30,
      "ema": 240,
      "value_multiplier": 2
    }
  }
}
```

**启动**：
```bash
python zhen_2.py
```

**区别**：与zhen.py相比，zhen_2.py在震荡市场中挂单距离更合理。

---

### 3. 激进型/高频爱好者 → 使用 `zhen_orderbook.py`

**特点**：
- ⚡ 10秒中频交易（可配置5-30秒）
- 📊 实时订单簿深度分析
- 🎯 基于订单簿失衡（OBI）生成信号
- 🧠 多维度置信度评分

**⚠️ 重要提示**：
- **仅适合高流动性品种**：BTC-USDT-SWAP, ETH-USDT-SWAP
- **小币种不推荐**：订单簿薄，信号噪音大
- **延迟敏感**：API延迟100-500ms，不是真正的HFT（微秒级）

**推荐配置**：
```json
{
  "monitor_interval": 10,
  "leverage": 10,
  "tradingPairs": {
    "BTC-USDT-SWAP": {
      "long_amount_usdt": 50,
      "short_amount_usdt": 50,
      "ema": 0
    }
  }
}
```

**启动**：
```bash
python zhen_orderbook.py
```

**日志查看**：
```bash
tail -f log/okx_orderbook.log
```

**核心指标解读**：
- **OBI > 0.3**：买盘压力大，生成买入信号
- **OBI < -0.3**：卖盘压力大，生成卖出信号
- **置信度 ≥ 0.7**：执行交易
- **置信度 < 0.7**：观望

---

### 4. 高级/量化研究 → 使用 `zhen_ml.py` ⭐新增

**特点**：
- 🤖 基于LightGBM机器学习模型
- 📊 融合40+维度特征（订单簿+技术指标+Ticker）
- 📚 持续学习，自动适应市场
- 🎯 每24小时自动重训练

**⚠️ 重要提示**：
- **需要先收集数据**：运行6-12小时收集训练数据
- **有一定技术门槛**：需理解机器学习基本概念
- **仅推荐BTC/ETH**：小币种数据噪音大

**使用流程**：

**阶段1：数据收集（6-12小时）**

```python
# 编辑 zhen_ml.py
DATA_COLLECTION_MODE = True  # 启用数据收集
```

```bash
# 运行数据收集
python zhen_ml.py

# 检查样本数（需要≥1000）
wc -l ml_data/BTC_USDT_SWAP_data.csv
```

**阶段2：模型训练（自动）**

当样本数≥1000时，系统自动训练。查看日志：

```bash
tail -f log/okx_ml.log

# 输出示例：
# BTC-USDT-SWAP 模型训练完成 - 准确率: 0.652
```

**阶段3：实盘交易**

```python
# 编辑 zhen_ml.py
DATA_COLLECTION_MODE = False  # 关闭数据收集
PREDICTION_THRESHOLD = 0.6    # 预测置信度阈值
```

```bash
# 启动交易
python zhen_ml.py

# 实时监控
tail -f log/okx_ml.log

# 输出示例：
# BTC-USDT-SWAP ML预测: 上涨, 置信度: 73%
# BTC-USDT-SWAP 下单成功: buy @ 98765.28
```

**配置示例**：

```json
{
  "monitor_interval": 10,
  "leverage": 10,
  "tradingPairs": {
    "BTC-USDT-SWAP": {
      "long_amount_usdt": 50,
      "short_amount_usdt": 50
    }
  }
}
```

**回测工具**：

```bash
# 回测模型表现
python backtest_ml.py \
  --data ml_data/BTC_USDT_SWAP_data.csv \
  --model ml_models/BTC_USDT_SWAP_model.pkl \
  --capital 1000 \
  --threshold 0.6

# 输出：胜率、收益率、夏普比率等
```

**详细文档**：查看 `ML_STRATEGY.md`

---

## 混合使用策略（推荐）

**最优组合**：`zhen_2.py` (主力) + `zhen_orderbook.py` (补充)

### 配置方案

#### 方案A：分不同交易对运行

**终端1**：运行 zhen_2.py
```json
// config.json
{
  "tradingPairs": {
    "SOL-USDT-SWAP": {...},
    "LINK-USDT-SWAP": {...}
  }
}
```

**终端2**：运行 zhen_orderbook.py
```json
// config_orderbook.json (需修改zhen_orderbook.py加载此文件)
{
  "tradingPairs": {
    "BTC-USDT-SWAP": {...},
    "ETH-USDT-SWAP": {...}
  }
}
```

#### 方案B：同一交易对，错峰运行

**终端1**：zhen_2.py，60秒周期，整点运行
**终端2**：zhen_orderbook.py，10秒周期，持续运行

通过监控日志避免同时下单冲突。

---

## 配置文件详解

### 核心参数

```json
{
  "okx": {
    "apiKey": "your-api-key",
    "secret": "your-secret",
    "password": "your-password"
  },
  "monitor_interval": 60,          // 监控周期（秒）
  "leverage": 10,                  // 杠杆倍数
  "feishu_webhook": "https://...", // 飞书通知webhook（可选）

  "tradingPairs": {
    "BTC-USDT-SWAP": {
      "long_amount_usdt": 50,      // 做多金额（USDT）
      "short_amount_usdt": 50,     // 做空金额（USDT）
      "ema": 240,                  // EMA周期，0表示双向挂单
      "value_multiplier": 2        // 挂单距离乘数
    }
  }
}
```

### 参数调优建议

| 参数 | 保守 | 平衡 | 激进 |
|------|------|------|------|
| `monitor_interval` | 60 | 60 | 10-20 |
| `leverage` | 5 | 10 | 15-20 |
| `long_amount_usdt` | 20 | 50 | 100+ |
| `value_multiplier` | 1.5 | 2 | 2.5 |
| `ema` | 240 | 240 | 0（订单簿策略） |

---

## 监控与日志

### 日志文件位置

```
log/okx.log           # zhen.py
log/okx2.log          # zhen_2.py
log/okx_orderbook.log # zhen_orderbook.py
```

### 实时查看

```bash
# 查看最新50行
tail -n 50 log/okx2.log

# 实时滚动
tail -f log/okx2.log

# 筛选错误
grep "ERROR" log/okx2.log
```

### 关键日志示例

**zhen_2.py**：
```
2025-11-18 10:00:00 - INFO - BTC-USDT-SWAP EMA240: 98000.123, 当前价格: 98500.456, 趋势: 多头
2025-11-18 10:00:01 - INFO - BTC-USDT-SWAP ATR: 500.12, 价格/ATR比值: 1.970, 平均振幅: 0.85%
2025-11-18 10:00:02 - INFO - BTC-USDT-SWAP 做多目标价: 97520.345 (-1.00%), 做空目标价: 99480.567 (+1.00%)
```

**zhen_orderbook.py**：
```
2025-11-18 10:00:00 - INFO - BTC-USDT-SWAP 信号: BUY, 置信度: 82%, 原因: 买盘压力大(OBI=0.456); 买盘深度优势(比例=2.13)
2025-11-18 10:00:00 - INFO - BTC-USDT-SWAP 特征 - OBI: 0.456, 价差: 0.50, WAP: 98765.43, 买深度: 12.34, 卖深度: 5.79
2025-11-18 10:00:01 - INFO - BTC-USDT-SWAP 挂买单: 价格=98765.28, 金额=41.00 USDT
```

---

## 常见问题

### Q1: 三个策略可以同时运行吗？

**A**: 可以，但需要注意：
1. **不同交易对**：最安全，推荐
2. **同一交易对**：可能冲突，需手动协调或修改代码添加订单冲突检测

### Q2: 订单簿策略为什么不适合小币种？

**A**: 小币种订单簿深度不足，导致：
- OBI波动剧烈，噪音大
- 大单容易操纵市场
- 滑点严重

建议只用于BTC/ETH等头部品种。

### Q3: 如何调整策略的激进程度？

**调整方向**：
- **更保守**：
  - 降低 `leverage`（5 → 3）
  - 降低 `long_amount_usdt`（50 → 20）
  - 提高 `value_multiplier`（2 → 2.5）挂单距离更远
  - 使用 `zhen.py` 而非 `zhen_2.py`

- **更激进**：
  - 提高 `leverage`（10 → 15）
  - 提高 `long_amount_usdt`（50 → 100）
  - 降低 `value_multiplier`（2 → 1.5）挂单距离更近
  - 缩短 `monitor_interval`（60 → 30）
  - 使用 `zhen_orderbook.py`

### Q4: 如何设置止盈止损？

**A**: 当前策略不主动持仓，采用"挂单等待成交"模式，无需传统止损。

如需主动持仓+止损，可修改代码：
1. 成交后不立即取消订单
2. 监控持仓盈亏
3. 达到阈值时市价平仓

（此功能计划在未来版本添加）

### Q5: API Key 权限需要哪些？

**必需权限**：
- ✅ 读取（查询订单簿、K线、持仓）
- ✅ 交易（下单、撤单）
- ✅ 资金划转（设置杠杆）

**不需要**：
- ❌ 提币

### Q6: 飞书通知如何配置？

**步骤**：
1. 在飞书群聊中添加"自定义机器人"
2. 复制webhook地址
3. 填入 `config.json` 的 `feishu_webhook` 字段

**示例**：
```json
{
  "feishu_webhook": "https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxxxx"
}
```

---

## 性能优化建议

### 1. 降低日志级别（生产环境）

修改代码：
```python
logger.setLevel(logging.WARNING)  # 只记录警告和错误
```

### 2. 增加批处理大小（多交易对）

```python
DEFAULT_BATCH_SIZE = 10  # 从5改为10
```

### 3. 使用更快的网络

- 使用云服务器（阿里云/AWS香港节点）
- 避免家庭网络不稳定

---

## 安全检查清单

✅ **配置文件安全**：
- [ ] `config.json` 已添加到 `.gitignore`
- [ ] API Key 权限设置正确（不包含提币）
- [ ] 设置了IP白名单（OKX后台）

✅ **资金安全**：
- [ ] 使用子账户，避免全部资金在一个账户
- [ ] 初期小金额测试（`long_amount_usdt: 10`）
- [ ] 设置了账户总资金限额

✅ **程序安全**：
- [ ] 代码理解透彻，知道每行在做什么
- [ ] 有紧急停止机制（Ctrl+C）
- [ ] 日志定期检查（每天至少一次）

---

## 下一步

1. **阅读详细文档**：
   - `OPTIMIZATION_NOTES.md`：代码优化说明
   - `ORDERBOOK_STRATEGY.md`：订单簿策略深度解析

2. **测试环境验证**：
   - 使用OKX模拟盘（如果有）
   - 或小金额实盘测试（10 USDT起）

3. **监控与调优**：
   - 运行1周后，分析日志统计
   - 根据成交率和盈亏调整参数

4. **扩展学习**：
   - 学习更多HFT概念（推荐阅读：Algorithmic Trading by Cartea）
   - 研究机器学习信号融合

---

## 专业工具 ⭐新增

### 高级回测引擎

精确模拟真实交易环境，包含滑点、手续费、止损止盈等。

```bash
# 运行高级回测
python advanced_backtest.py \
  --data ml_data/BTC_USDT_SWAP_data.csv \
  --model ml_models/BTC_USDT_SWAP_model.pkl \
  --capital 10000 \
  --stop-loss 0.02 \
  --take-profit 0.03

# 输出：
# - 详细回测报告（夏普比率、最大回撤等）
# - backtest_trades.csv（交易明细）
# - backtest_equity.csv（权益曲线）
```

**核心特性**：
- ✅ 双手续费（Maker/Taker）
- ✅ 真实滑点模拟
- ✅ 自动止损止盈
- ✅ 10+风险指标

### 数据可视化

生成专业的回测图表报告。

```bash
# 生成可视化报告
python visualize_backtest.py

# 输出：
# - backtest_report.png（综合报告）
# - backtest_analysis.png（详细分析）
```

**包含图表**：
- 📊 权益曲线
- 📉 回撤分析
- 📈 交易分布
- 🔥 月度热力图
- 🥧 退出原因分析

### 测试套件

确保代码质量和稳定性。

```bash
# 运行所有测试
pytest tests/ -v

# 生成覆盖率报告
pytest tests/ --cov=. --cov-report=html
```

**详细文档**：查看 `ADVANCED_TOOLS.md`

---

## 技术支持

- **日志分析**：查看对应的 `.log` 文件
- **飞书通知**：重要错误会自动推送
- **代码问题**：检查 Python 依赖（`pip install -r requirements.txt`）

## 文档导航

| 文档 | 内容 |
|------|------|
| **QUICK_START.md** | 快速开始（本文档） |
| **ORDERBOOK_STRATEGY.md** | 订单簿策略详解 |
| **ML_STRATEGY.md** | 机器学习策略完整指南 |
| **ADVANCED_TOOLS.md** ⭐ | 高级回测和可视化工具 |
| **OPTIMIZATION_NOTES.md** | 代码优化说明 |

**祝交易顺利！** 🚀
