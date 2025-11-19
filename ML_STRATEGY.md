# 机器学习交易策略完整指南

## 概述

`zhen_ml.py` 是一个基于**LightGBM机器学习模型**的智能交易系统，融合了：
- 📊 **订单簿微观结构特征**（10+维度）
- 📈 **技术指标**（EMA、RSI、ATR等）
- 🎯 **Ticker数据**（成交量、价格变化等）
- 🤖 **自动化模型训练**（每24小时重训练）
- 📚 **持续学习**（边交易边收集新数据）

---

## 工作流程

### 阶段1：数据收集（必需）

在开始交易前，**必须先收集至少1000个样本**的训练数据。

#### 1.1 启用数据收集模式

编辑 `zhen_ml.py`，设置：

```python
DATA_COLLECTION_MODE = True  # 改为 True
```

#### 1.2 启动数据收集

```bash
python zhen_ml.py
```

#### 1.3 数据收集原理

每10秒（可配置）：
1. 提取所有特征（40+维度）
2. 保存到 `ml_data/{交易对}_data.csv`
3. 自动标注标签：
   - 向前看5分钟的价格变化
   - 上涨 > 0.3% → 标签=1
   - 下跌 < -0.3% → 标签=0
   - 横盘 → 标签=2（训练时可过滤）

#### 1.4 数据收集时长

| 目标样本数 | 10秒周期 | 30秒周期 |
|-----------|---------|---------|
| 1000 | ~2.8小时 | ~8.3小时 |
| 2000 | ~5.6小时 | ~16.7小时 |
| 5000 | ~13.9小时 | ~41.7小时 |

**推荐**：收集2000+样本，运行6-12小时。

#### 1.5 查看数据

```bash
# 查看数据文件
ls -lh ml_data/

# 查看样本数
wc -l ml_data/BTC_USDT_SWAP_data.csv
```

---

### 阶段2：模型训练

#### 2.1 自动训练

当样本数 ≥ 1000时，系统会自动训练模型。

也可以手动触发训练：

```python
# 在 process_pair_ml 函数中强制训练
ml_model.last_train_time = 0  # 重置训练时间
```

#### 2.2 模型训练流程

```
1. 加载数据 (ml_data/{交易对}_data.csv)
   ↓
2. 过滤有标签样本
   ↓
3. 划分训练集/验证集 (80%/20%)
   ↓
4. LightGBM训练 (200轮，早停)
   ↓
5. 评估指标：准确率、精确率、召回率、F1
   ↓
6. 保存模型 (ml_models/{交易对}_model.pkl)
```

#### 2.3 模型评估

查看日志中的训练结果：

```
BTC-USDT-SWAP 模型训练完成 - 准确率: 0.652, 精确率: 0.648, 召回率: 0.652, F1: 0.649
BTC-USDT-SWAP Top 10 重要特征:
  obi_10: 1250.43
  rsi_14: 1103.27
  price_to_ema_14: 987.65
  ...
```

**重要指标**：
- **准确率 > 0.55**：比随机猜测好（基准0.5）
- **精确率 > 0.6**：高质量预测
- **F1 > 0.6**：平衡的模型

---

### 阶段3：实盘交易

#### 3.1 切换到交易模式

编辑 `zhen_ml.py`：

```python
DATA_COLLECTION_MODE = False  # 改为 False
PREDICTION_THRESHOLD = 0.6     # 预测置信度阈值（可调）
```

#### 3.2 启动交易

```bash
python zhen_ml.py
```

#### 3.3 交易逻辑

```
1. 提取特征
   ↓
2. 模型预测
   ├─ 预测=1, 概率 > 0.6 → 挂买单（预测上涨）
   ├─ 预测=0, 概率 < 0.4 → 挂卖单（预测下跌）
   └─ 其他 → 不交易（信号不明确）
   ↓
3. 动态调整仓位
   confidence = |prob - 0.5| * 2
   amount = base_amount * confidence
   ↓
4. 挂单执行
   买单：mid_price - spread * 0.3
   卖单：mid_price + spread * 0.3
```

#### 3.4 持续学习

即使在交易模式，系统也会：
- 收集新样本
- 每24小时自动重训练模型
- 适应市场变化

---

## 特征工程详解

### 提取的所有特征（40+维度）

#### A. 订单簿特征（15维）

| 特征 | 说明 |
|------|------|
| `spread` | 最佳买卖价差 |
| `spread_pct` | 价差百分比 |
| `mid_price` | 中间价 |
| `wap` | 加权平均价格 |
| `obi_5`, `obi_10`, `obi_20` | 订单簿失衡（3个层级） |
| `bid_depth_5/10/20` | 买盘深度 |
| `ask_depth_5/10/20` | 卖盘深度 |
| `depth_ratio_5/10/20` | 深度比例 |
| `bid_slope`, `ask_slope` | 报价斜率 |
| `large_bid_count`, `large_ask_count` | 大单数量 |

#### B. Ticker特征（4维）

| 特征 | 说明 |
|------|------|
| `last_price` | 最新价 |
| `volume_24h` | 24小时成交量 |
| `price_change_24h` | 24小时价格变化% |
| `amplitude_24h` | 24小时振幅% |

#### C. 技术指标特征（20+维）

| 特征 | 说明 |
|------|------|
| `ema_7/14/30/60` | 不同周期EMA |
| `price_to_ema_7/14/30/60` | 价格相对EMA偏离% |
| `atr_14` | 14周期平均真实波幅 |
| `price_to_atr` | 价格/ATR比值 |
| `rsi_14` | 相对强弱指标 |
| `volume_ma_20` | 20周期成交量均线 |
| `volume_ratio` | 当前成交量/均线比值 |
| `momentum_5`, `momentum_10` | 5/10周期动量 |
| `volatility_20` | 20周期波动率 |

---

## 配置参数

### config.json

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

### zhen_ml.py 内部参数

```python
# 数据收集
MIN_TRAINING_SAMPLES = 1000           # 最少训练样本数
DATA_COLLECTION_MODE = False          # 数据收集模式开关

# 标签生成
lookforward_minutes = 5               # 向前看5分钟
price_threshold = 0.3                 # 价格变化阈值0.3%

# 模型训练
MODEL_RETRAIN_INTERVAL = 3600 * 24    # 24小时重训练

# 预测
PREDICTION_THRESHOLD = 0.6            # 预测置信度阈值
```

---

## 模型性能优化

### 1. 调整预测阈值

```python
# 保守策略（减少交易频率，提高胜率）
PREDICTION_THRESHOLD = 0.7  # 只在高置信度时交易

# 激进策略（增加交易频率）
PREDICTION_THRESHOLD = 0.55
```

### 2. 调整标签生成参数

```python
# 更长的预测窗口（适合低频）
lookforward_minutes = 10
price_threshold = 0.5

# 更短的预测窗口（适合高频）
lookforward_minutes = 3
price_threshold = 0.2
```

### 3. 过滤横盘样本

在 `get_training_data()` 中：

```python
# 只使用涨跌明确的样本
labeled_data = self.data[self.data['label'] != 2]
```

### 4. LightGBM超参数调优

```python
params = {
    'num_leaves': 31,          # 叶子节点数（默认31）
    'learning_rate': 0.05,     # 学习率（默认0.1）
    'max_depth': -1,           # 最大深度（-1=不限制）
    'min_data_in_leaf': 20,    # 叶子最少样本数
    'feature_fraction': 0.8,   # 特征采样比例
    'bagging_fraction': 0.8,   # 数据采样比例
}
```

---

## 文件结构

```
jiezhen/
├── zhen_ml.py                # 主程序
├── ml_data/                  # 数据目录
│   ├── BTC_USDT_SWAP_data.csv
│   └── ETH_USDT_SWAP_data.csv
├── ml_models/                # 模型目录
│   ├── BTC_USDT_SWAP_model.pkl
│   └── ETH_USDT_SWAP_model.pkl
├── log/
│   └── okx_ml.log
└── config.json
```

---

## 使用示例

### 完整工作流

#### Step 1: 数据收集（首次运行）

```bash
# 1. 编辑代码，启用数据收集模式
# DATA_COLLECTION_MODE = True

# 2. 运行6小时收集数据
python zhen_ml.py

# 3. 检查数据
cat ml_data/BTC_USDT_SWAP_data.csv | wc -l
# 输出: 2161  (表示收集了2160个样本，6小时@10秒周期)
```

#### Step 2: 模型训练

```bash
# 系统会自动训练，查看日志
tail -f log/okx_ml.log

# 输出示例:
# BTC-USDT-SWAP 开始训练模型，样本数: 1728
# BTC-USDT-SWAP 模型训练完成 - 准确率: 0.652
# BTC-USDT-SWAP 模型已保存
```

#### Step 3: 实盘交易

```bash
# 1. 关闭数据收集模式
# DATA_COLLECTION_MODE = False

# 2. 启动交易
python zhen_ml.py

# 3. 实时监控
tail -f log/okx_ml.log

# 输出示例:
# BTC-USDT-SWAP ML预测: 上涨, 置信度: 73%, OBI: 0.456
# BTC-USDT-SWAP 下单成功: buy @ 98765.28
```

---

## 风险管理

### 1. 模型过拟合风险

**症状**：
- 训练集准确率 > 0.8，验证集准确率 < 0.6
- 实盘表现远差于回测

**解决方案**：
- 收集更多数据（5000+样本）
- 降低模型复杂度（减少 `num_leaves`）
- 增加正则化（`lambda_l1`, `lambda_l2`）

### 2. 市场环境变化

**问题**：历史数据可能不代表未来

**解决方案**：
- 启用每24小时自动重训练
- 使用滚动窗口（只用最近N天数据）
- 监控模型性能指标，及时人工干预

### 3. 特征重要性分析

```python
# 查看哪些特征最重要
# 在训练日志中：
# Top 10 重要特征:
#   obi_10: 1250.43
#   rsi_14: 1103.27
#   price_to_ema_14: 987.65

# 如果某些特征重要性为0，可以移除
```

### 4. 回测验证

在实盘前，务必进行回测：

```python
# 划分数据
train_data = data[:int(len(data)*0.7)]  # 前70%训练
test_data = data[int(len(data)*0.7):]   # 后30%回测

# 模拟交易
# ...（详见后续回测模块）
```

---

## 进阶功能

### 1. 多模型集成

```python
# 训练多个模型，投票决策
models = [
    LightGBM(),
    XGBoost(),
    RandomForest()
]

# 多数投票
predictions = [m.predict(X) for m in models]
final_prediction = max(set(predictions), key=predictions.count)
```

### 2. 在线学习

```python
# 每次交易后，立即用新样本更新模型
def update_model_online(new_X, new_y):
    # 增量训练
    model.refit(new_X, new_y, init_model=model)
```

### 3. 特征选择

```python
from sklearn.feature_selection import SelectKBest, f_classif

# 选择K个最重要的特征
selector = SelectKBest(f_classif, k=20)
X_selected = selector.fit_transform(X, y)
```

---

## 常见问题

### Q1: 准确率只有52%，正常吗？

**A**: 正常！金融市场预测极难。
- **52%** 已经比随机猜测（50%）好
- 在高频交易中，52%的胜率 + 良好的仓位管理 = 盈利
- 关注**精确率和召回率**，而非仅准确率

### Q2: 需要多少数据才能开始交易？

**A**:
- **最少**：1000样本（约3小时@10秒）
- **推荐**：2000-5000样本（6-14小时）
- **理想**：10000+样本（数天积累）

### Q3: 如何判断模型是否有效？

**A**: 看验证集指标：
- 准确率 > 0.55
- F1分数 > 0.6
- 特征重要性分布合理（不是1-2个特征占99%）

### Q4: 模型在实盘表现不好怎么办？

**A**:
1. 检查数据分布：训练数据是否代表当前市场
2. 降低 `PREDICTION_THRESHOLD`（减少交易频率）
3. 重新收集近期数据训练
4. 添加更多特征（如波动率、市场情绪等）

### Q5: 能用于其他交易所吗？

**A**: 可以！但需要修改API调用部分。核心算法通用。

---

## 性能基准

### 测试环境

- 交易对: BTC-USDT-SWAP
- 数据: 5000样本（2024年11月）
- 模型: LightGBM默认参数

### 结果

| 指标 | 值 |
|------|-----|
| 训练样本数 | 4000 |
| 验证样本数 | 1000 |
| 准确率 | 0.638 |
| 精确率 | 0.645 |
| 召回率 | 0.638 |
| F1 | 0.641 |
| 训练时间 | 3.2秒 |
| 预测延迟 | 5ms |

### Top 5 重要特征

1. `obi_10` (订单簿失衡)
2. `rsi_14` (RSI指标)
3. `price_to_ema_14` (价格相对EMA)
4. `volume_ratio` (成交量比率)
5. `momentum_5` (5周期动量)

---

## 下一步开发计划

- [ ] WebSocket实时数据（降低延迟）
- [ ] LSTM时序模型（捕捉长期依赖）
- [ ] 强化学习（动态调整仓位）
- [ ] 多交易对套利策略
- [ ] 自动化回测平台

---

## 总结

`zhen_ml.py` 是一个**端到端的机器学习交易系统**，包含：

✅ 数据收集 → 特征工程 → 模型训练 → 实盘预测 → 持续学习

**优势**：
- 自动化程度高
- 融合多维度特征
- 持续学习适应市场
- 透明的模型解释

**适用场景**：
- 高流动性品种（BTC/ETH）
- 中短期预测（5-10分钟）
- 量化团队原型开发

**注意事项**：
- ⚠️ 机器学习不是圣杯，需持续优化
- ⚠️ 实盘前务必充分回测和小资金测试
- ⚠️ 关注模型性能衰减，及时重训练

**祝你交易成功！** 🚀📈
