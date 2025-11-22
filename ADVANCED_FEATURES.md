# 高级功能文档

## 概述

本文档介绍交易机器人v2.0的高级优化功能，包括机器学习预测、智能执行、高级风控和实时监控。

---

## 🎯 新增功能总览

| 功能模块 | 文件 | 说明 |
|---------|------|------|
| 机器学习预测 | ml_predictor.py | 使用技术指标预测短期价格走势 |
| 智能执行优化 | execution_optimizer.py | TWAP/VWAP算法，减少市场冲击 |
| 高级风险控制 | advanced_risk.py | 止损/止盈、动态仓位管理 |
| 实时监控系统 | monitoring.py | 性能监控、异常检测、智能预警 |
| 高级主程序 | main_advanced.py | 集成所有高级功能 |

---

## 1. 机器学习价格预测 🤖

### 功能说明

使用随机森林或梯度提升模型，基于技术指标预测短期价格走势（上涨/下跌/中性）。

### 特征工程

自动提取以下特征：
- **价格相关**：价格/EMA比值、ATR比值、振幅
- **趋势特征**：5/10/20根K线趋势
- **波动率特征**：收益率标准差
- **动量特征**：RSI简化版
- **成交量特征**：成交量比率
- **K线形态**：实体、影线比例

### 使用方法

```python
from ml_predictor import MLPredictor

# 初始化预测器
predictor = MLPredictor(
    model_type='random_forest',  # 或 'gradient_boosting'
    confidence_threshold=0.6
)

# 预测
prediction = predictor.predict(
    inst_id='BTC-USDT-SWAP',
    klines=klines,
    current_price=current_price,
    ema=ema_value,
    atr=atr_value,
    amplitude=amplitude
)

if prediction and prediction.confidence > 0.6:
    print(f"方向: {prediction.direction}")  # 'bullish', 'bearish', 'neutral'
    print(f"置信度: {prediction.confidence}")
    print(f"概率: {prediction.probabilities}")
```

### 模型训练

```python
# 准备训练数据
training_data = [
    {
        'features': {...},  # 特征字典
        'label': 2  # 0=下跌, 1=中性, 2=上涨
    },
    ...
]

# 训练模型
predictor.train(
    inst_id='BTC-USDT-SWAP',
    training_data=training_data,
    save_model=True
)
```

### 模型评估

训练完成后会输出：
- 训练集准确率
- 测试集准确率

模型文件保存在 `models/` 目录。

### 备选方案

如果scikit-learn未安装，自动使用 `SimplePredictor` - 基于规则的简单预测器。

---

## 2. 智能订单执行优化 ⚡

### 功能说明

通过将大额订单拆分成多个小订单，在一段时间内逐步执行，减少市场冲击。

### 支持的算法

| 算法 | 说明 | 适用场景 |
|------|------|----------|
| **TWAP** | 时间加权平均价格 | 均匀拆分，适合平稳市场 |
| **VWAP** | 成交量加权平均价格 | 根据成交量分布拆分 |
| **Adaptive** | 自适应执行 | 根据市场流动性动态调整 |

### 使用示例

#### 创建TWAP执行计划

```python
from execution_optimizer import ExecutionOptimizer

optimizer = ExecutionOptimizer()

# 创建TWAP计划
plan = optimizer.create_twap_plan(
    inst_id='BTC-USDT-SWAP',
    total_amount=1000.0,  # USDT
    duration_minutes=5,   # 5分钟内执行
    num_slices=5          # 拆分成5个订单
)

# 获取下一个应该执行的切片
slice_order = optimizer.get_next_slice('BTC-USDT-SWAP')
if slice_order:
    # 执行订单
    place_order(size=slice_order.size)

    # 标记为已执行
    optimizer.mark_slice_executed(
        'BTC-USDT-SWAP',
        slice_order,
        execution_price=current_price
    )

# 查看执行统计
stats = optimizer.get_execution_stats('BTC-USDT-SWAP')
print(f"进度: {stats['progress']:.1f}%")
print(f"平均成交价: {stats['avg_price']}")
```

#### 创建VWAP执行计划

```python
# 自定义成交量分布（可选）
volume_profile = [1.5, 1.2, 1.0, 1.2, 1.5]  # U型分布

plan = optimizer.create_vwap_plan(
    inst_id='ETH-USDT-SWAP',
    total_amount=500.0,
    volume_profile=volume_profile,
    duration_minutes=3
)
```

#### 自适应执行

```python
plan = optimizer.create_adaptive_plan(
    inst_id='BTC-USDT-SWAP',
    total_amount=800.0,
    current_spread=0.01,  # 当前买卖价差
    avg_spread=0.005,     # 平均买卖价差
    duration_minutes=5
)
```

### 自动拆分判断

```python
# 检查是否需要拆分
if optimizer.should_split_order(amount_usdt=1000, market_volatility=2.0):
    # 创建执行计划
    plan = optimizer.create_twap_plan(...)
else:
    # 直接执行
    place_order(...)
```

---

## 3. 高级风险控制和止损机制 🛡️

### 功能说明

提供多种止损策略、止盈机制和动态仓位管理。

### 止损类型

| 类型 | 说明 | 优势 |
|------|------|------|
| **FIXED** | 固定百分比止损 | 简单，适合新手 |
| **TRAILING** | 移动止损 | 锁定利润，适合趋势行情 |
| **ATR_BASED** | 基于ATR的止损 | 自适应波动率 |

### 配置示例

```python
from advanced_risk import (
    AdvancedRiskManager,
    StopLossConfig,
    TakeProfitConfig,
    PositionSizing,
    StopLossType
)

# 止损配置
stop_loss_config = StopLossConfig(
    enabled=True,
    stop_loss_type=StopLossType.TRAILING,  # 移动止损
    trailing_percentage=3.0  # 移动止损3%
)

# 止盈配置
take_profit_config = TakeProfitConfig(
    enabled=True,
    target_percentage=10.0,  # 目标盈利10%
    partial_take_profit=True,  # 启用部分止盈
    partial_percentage=50.0  # 止盈50%仓位
)

# 仓位管理配置
position_sizing = PositionSizing(
    use_kelly_criterion=False,  # 是否使用凯利公式
    risk_per_trade_percentage=2.0  # 每笔交易风险2%
)

# 初始化
risk_manager = AdvancedRiskManager(
    account_balance=10000.0,
    stop_loss_config=stop_loss_config,
    take_profit_config=take_profit_config,
    position_sizing=position_sizing
)
```

### 使用示例

#### 动态仓位计算

```python
# 计算推荐仓位大小
position_size = risk_manager.calculate_position_size(
    inst_id='BTC-USDT-SWAP',
    entry_price=50000,
    stop_loss_price=48500,
    win_rate=0.55,  # 历史胜率
    avg_win_loss_ratio=1.8  # 平均盈亏比
)

print(f"建议仓位: {position_size:.2f} USDT")
```

#### 添加止损订单

```python
# 开仓时添加止损
risk_manager.add_stop_loss_order(
    inst_id='BTC-USDT-SWAP',
    entry_price=50000,
    position_side='long',
    size_usdt=500,
    atr=200  # ATR值（可选）
)
```

#### 更新移动止损

```python
# 价格变动时更新移动止损
new_stop = risk_manager.update_trailing_stop(
    inst_id='BTC-USDT-SWAP',
    current_price=51000
)

if new_stop:
    print(f"止损已更新至: {new_stop}")
```

#### 检查止损触发

```python
# 每次价格更新时检查
triggered, reason = risk_manager.check_stop_loss(
    inst_id='BTC-USDT-SWAP',
    current_price=48000
)

if triggered:
    print(f"止损触发: {reason}")
    # 平仓
    close_position()
```

#### 检查止盈触发

```python
triggered, percentage, reason = risk_manager.check_take_profit(
    inst_id='BTC-USDT-SWAP',
    entry_price=50000,
    current_price=55000,
    position_side='long'
)

if triggered:
    print(f"止盈触发: {reason}")
    print(f"平仓比例: {percentage}%")
    # 部分或全部平仓
    close_position(percentage=percentage)
```

### 风险保护

```python
# 检查是否应该降低风险
should_reduce, reason = risk_manager.should_reduce_risk()
if should_reduce:
    print(f"风险警告: {reason}")
    # 减少仓位或暂停交易
```

---

## 4. 实时监控和预警系统 📊

### 功能说明

提供全面的性能监控、系统监控和智能预警功能。

### 监控指标

#### 性能指标
- 总交易次数、盈利/亏损次数
- 胜率、盈亏比
- 最大盈利/亏损
- 平均交易时长
- 夏普比率

#### 系统指标
- API调用总数、失败率
- 平均响应时间
- 缓存命中率

### 使用示例

```python
from monitoring import PerformanceMonitor, AlertLevel

# 初始化监控器
monitor = PerformanceMonitor(
    history_size=1000,
    alert_callback=handle_alert  # 预警回调函数
)

# 记录交易
monitor.record_trade(
    inst_id='BTC-USDT-SWAP',
    side='long',
    entry_price=50000,
    exit_price=51000,
    size_usdt=500,
    profit=100,  # 盈亏
    duration_seconds=3600  # 持续时间
)

# 记录API调用
monitor.record_api_call(
    success=True,
    response_time_ms=150,
    retried=False
)

# 更新权益曲线
monitor.update_equity(equity=10500)

# 获取性能报告
report = monitor.get_performance_report()
print(report)
# {
#     'total_trades': 50,
#     'win_rate': '60.00%',
#     'profit_factor': '1.85',
#     ...
# }

# 获取系统报告
sys_report = monitor.get_system_report()
print(sys_report)
# {
#     'api_fail_rate': '2.50%',
#     'avg_response_time': '180ms',
#     'cache_hit_rate': '75.0%',
#     ...
# }

# 获取最近预警
alerts = monitor.get_recent_alerts(minutes=60, level=AlertLevel.WARNING)
for alert in alerts:
    print(f"{alert.level.value}: {alert.message}")

# 导出监控数据
monitor.export_metrics('monitoring_report.json')
```

### 预警触发条件

| 预警类型 | 触发条件 | 级别 |
|---------|---------|------|
| 连续亏损 | 连续5次亏损 | WARNING |
| 胜率过低 | 胜率<30%（>=20笔交易后） | WARNING |
| 回撤过大 | 回撤>=20% | CRITICAL |
| API失败率高 | 失败率>=10% | ERROR |
| 响应时间长 | 平均响应>5000ms | WARNING |

### 预警回调

```python
def handle_alert(alert):
    """处理预警"""
    if alert.level == AlertLevel.CRITICAL:
        # 发送紧急通知
        send_urgent_notification(alert.message)
        # 暂停交易
        pause_trading()

    elif alert.level == AlertLevel.ERROR:
        # 发送错误通知
        send_error_notification(alert.message)

    # 记录到日志
    logger.warning(f"[{alert.category}] {alert.message}")
```

---

## 5. 高级主程序使用指南

### 运行高级版本

```bash
# 安装依赖（包含scikit-learn）
pip install -r requirements.txt

# 运行高级主程序
python main_advanced.py
```

### 与基础版本对比

| 特性 | 基础版本 (main.py) | 高级版本 (main_advanced.py) |
|------|-------------------|---------------------------|
| 技术指标计算 | ✅ | ✅ |
| 策略模块 | ✅ | ✅ |
| 基础风控 | ✅ | ✅ |
| **ML预测** | ❌ | ✅ |
| **智能执行** | ❌ | ✅ |
| **高级止损** | ❌ | ✅ |
| **动态仓位** | ❌ | ✅ |
| **实时监控** | ❌ | ✅ |
| **性能报告** | 基础 | 完整 |

### 功能开关

所有高级功能都可以独立开关：

```python
# ML预测：自动检测scikit-learn可用性
# 不可用时自动降级到SimplePredictor

# 智能执行：通过金额阈值控制
execution_optimizer.should_split_order(amount_usdt)

# 止损止盈：通过配置控制
StopLossConfig(enabled=True/False)
TakeProfitConfig(enabled=True/False)

# 监控：始终启用，但可以选择不导出
```

---

## 6. 配置建议

### 开发/测试环境

```python
# ML预测
confidence_threshold = 0.7  # 更高的置信度要求

# 执行优化
min_slice_size = 5.0  # 更小的切片
max_slices = 5  # 更少的切片

# 风险控制
StopLossConfig(
    trailing_percentage=2.0  # 更紧的止损
)
TakeProfitConfig(
    target_percentage=5.0,  # 更低的止盈目标
    partial_percentage=70.0  # 更大比例止盈
)
```

### 生产环境

```python
# ML预测
confidence_threshold = 0.6  # 平衡的置信度

# 执行优化
min_slice_size = 10.0
max_slices = 10

# 风险控制
StopLossConfig(
    trailing_percentage=3.0
)
TakeProfitConfig(
    target_percentage=10.0,
    partial_percentage=50.0
)
```

---

## 7. 性能优化建议

### ML模型优化

1. **定期重训练**：每周或每月使用最新数据重训练
2. **特征选择**：只保留重要特征，提高预测速度
3. **模型压缩**：使用较小的n_estimators（50-100）

### 执行优化建议

1. **小额订单**：<100 USDT不拆分
2. **中额订单**：100-500 USDT拆分3-5个
3. **大额订单**：>500 USDT拆分5-10个

### 监控性能优化

1. 历史数据使用deque，自动限制大小
2. 定期导出并清理历史数据
3. 只在关键事件触发回调

---

## 8. 故障排除

### ML预测不工作

**问题**：scikit-learn未安装

**解决**：
```bash
pip install scikit-learn>=1.2.0
```

**备选方案**：使用SimplePredictor（自动降级）

### 止损未触发

**检查清单**：
- [ ] StopLossConfig.enabled = True
- [ ] 已调用add_stop_loss_order()
- [ ] 定期调用check_stop_loss()

### 监控数据不准确

**原因**：未正确记录交易

**解决**：确保每笔交易都调用record_trade()

---

## 9. 最佳实践

### 1. 渐进式启用功能

```
第1周：只使用基础版本，熟悉策略
第2周：启用ML预测（观察模式，不影响交易）
第3周：启用智能执行优化
第4周：启用高级止损止盈
```

### 2. 监控指标阈值

```python
# 设置合理的阈值
monitor.thresholds = {
    'max_consecutive_losses': 3,  # 保守
    'max_drawdown_pct': 15.0,     # 保守
    'min_win_rate': 40.0,         # 合理
    'max_api_fail_rate': 5.0,     # 严格
    'max_response_time_ms': 3000  # 严格
}
```

### 3. 定期维护

```python
# 每日
- 检查监控报告
- 导出性能数据
- 检查预警

# 每周
- 重训练ML模型
- 分析交易记录
- 调整策略参数

# 每月
- 全面性能review
- 风险指标评估
- 代码和配置备份
```

---

## 10. 常见问题

**Q: ML预测准确率多高才能使用？**

A: 建议测试集准确率>55%，且confidence>0.6的预测才参考。

**Q: 智能执行会增加手续费吗？**

A: 会。拆分订单会增加交易次数，但减少市场冲击可能带来更好的成交价格。

**Q: 移动止损会过早止损吗？**

A: 可能。建议trailing_percentage设置在3-5%之间。

**Q: 监控数据会占用很多内存吗？**

A: 不会。使用deque限制历史数据大小（默认1000条）。

**Q: 可以只使用某些高级功能吗？**

A: 可以。所有模块都是独立的，可以选择性使用。

---

## 总结

高级功能显著提升了交易机器人的智能化水平：

✅ **ML预测** - 辅助决策，提高胜率
✅ **智能执行** - 减少冲击，优化成交
✅ **高级风控** - 保护资金，锁定利润
✅ **实时监控** - 及时发现问题，优化策略

建议渐进式启用，持续监控效果，不断优化参数。
