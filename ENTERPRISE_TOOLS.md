# 企业级量化交易工具套件

本文档介绍最新添加的企业级工具，助力构建专业的量化交易系统。

---

## 📊 工具概览

| 工具 | 文件 | 功能 | 优先级 |
|------|------|------|--------|
| WebSocket数据流 | `websocket_stream.py` | 实时市场数据 | ⭐⭐⭐ |
| 实时监控面板 | `monitor_dashboard.py` | 可视化监控 | ⭐⭐⭐ |
| 参数优化器 | `strategy_optimizer.py` | 自动调参 | ⭐⭐⭐ |
| 风险管理器 | `risk_manager.py` | 动态风控 | ⭐⭐⭐ |
| 组合管理器 | `portfolio_manager.py` | 多策略组合 | ⭐⭐ |
| Docker部署 | `docker-compose.yml` | 容器化部署 | ⭐⭐ |

---

## 🚀 1. WebSocket实时数据流

### 功能特性

- ✅ 实时订单簿数据（5档/400档）
- ✅ 实时Ticker行情
- ✅ 实时成交数据
- ✅ 自动重连机制
- ✅ 数据缓存
- ✅ 回调事件系统
- ✅ 心跳保持

### 性能提升

| 指标 | REST API | WebSocket | 提升 |
|------|----------|-----------|------|
| 延迟 | 100-500ms | 50-100ms | **5倍** |
| 更新频率 | 按需轮询 | 推送更新 | **实时** |
| 带宽 | 高（完整响应） | 低（增量更新） | **-60%** |

### 快速开始

```python
from websocket_stream import OKXWebSocket
import time

# 创建WebSocket客户端
ws_client = OKXWebSocket()

# 注册回调函数
def on_orderbook_update(data):
    print(f"订单簿更新: {data['instId']}")
    print(f"  最佳买价: {data['bids'][0][0]}")
    print(f"  最佳卖价: {data['asks'][0][0]}")

ws_client.register_callback('orderbook', on_orderbook_update)

# 连接并订阅
ws_client.connect()
ws_client.subscribe_orderbook('BTC-USDT-SWAP')
ws_client.subscribe_ticker('BTC-USDT-SWAP')

# 保持运行
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    ws_client.disconnect()
```

### 集成到策略

```python
# 在zhen_ml.py中使用
from websocket_stream import OKXWebSocket

ws = OKXWebSocket()
ws.register_callback('orderbook', handle_orderbook)
ws.connect()
ws.subscribe_orderbook('BTC-USDT-SWAP')

def handle_orderbook(data):
    # 提取特征
    features = extract_orderbook_features(data)
    # 预测
    prediction = model.predict(features)
    # 交易
    if prediction > threshold:
        place_order(...)
```

---

## 📈 2. Streamlit实时监控面板

### 功能特性

- ✅ 实时权益曲线
- ✅ 关键指标卡片（收益率、夏普、回撤等）
- ✅ 交易分析（盈亏分布、退出原因）
- ✅ 持仓状态
- ✅ 风险监控和告警
- ✅ 自动刷新（可配置间隔）
- ✅ 时间范围筛选
- ✅ 策略选择

### 启动方法

```bash
# 方法1: 直接运行
streamlit run monitor_dashboard.py

# 方法2: 指定端口
streamlit run monitor_dashboard.py --server.port=8501

# 方法3: Docker运行
docker-compose up -d trading-bot
```

访问：http://localhost:8501

### 界面预览

```
┌─────────────────────────────────────────────────────────┐
│              📈 量化交易实时监控面板                       │
├─────────────────────────────────────────────────────────┤
│  💰 当前权益    📊 总收益率    💵 今日盈亏    🎯 胜率    │
│  $10,500       +5.00%         +$50         62.5%        │
├─────────────────────────────────────────────────────────┤
│  📈 夏普比率    📉 最大回撤    🔢 总交易     📦 持仓    │
│  2.134         -3.21%         148          3            │
├─────────────────────────────────────────────────────────┤
│                                                           │
│  [权益曲线] [交易分析] [持仓状态] [风险监控]             │
│                                                           │
└─────────────────────────────────────────────────────────┘
```

### 数据源

面板从以下文件读取数据：
- `backtest_equity.csv` - 权益曲线数据
- `backtest_trades.csv` - 交易记录

确保回测时导出这些文件：

```python
from advanced_backtest import AdvancedBacktester

backtester = AdvancedBacktester(config)
# ... 运行回测 ...
backtester.export_equity_curve('backtest_equity.csv')
backtester.export_trades('backtest_trades.csv')
```

---

## 🎯 3. 策略参数优化器

### 功能特性

- ✅ **网格搜索** - 穷举所有参数组合
- ✅ **随机搜索** - 随机采样参数空间
- ✅ **贝叶斯优化** - 基于差分进化算法
- ✅ **遗传算法** - 模拟自然选择

### 优化算法对比

| 算法 | 优点 | 缺点 | 适用场景 |
|------|------|------|----------|
| 网格搜索 | 全局最优、可解释 | 计算量大 | 参数空间小 |
| 随机搜索 | 快速、易实现 | 可能错过最优 | 初步探索 |
| 贝叶斯优化 | 高效、全局搜索 | 复杂度高 | **推荐** |
| 遗传算法 | 全局搜索、鲁棒 | 计算量大 | 复杂参数空间 |

### 使用示例

```bash
# 网格搜索
python strategy_optimizer.py \
  --data ml_data/BTC-USDT-SWAP_features.csv \
  --model ml_models/lgb_model.txt \
  --method grid \
  --metric sharpe_ratio

# 贝叶斯优化（推荐）
python strategy_optimizer.py \
  --data ml_data/BTC-USDT-SWAP_features.csv \
  --model ml_models/lgb_model.txt \
  --method bayesian \
  --iterations 50 \
  --metric sharpe_ratio

# 遗传算法
python strategy_optimizer.py \
  --data ml_data/BTC-USDT-SWAP_features.csv \
  --model ml_models/lgb_model.txt \
  --method genetic \
  --iterations 100 \
  --metric profit_factor
```

### 编程接口

```python
from strategy_optimizer import StrategyOptimizer

# 创建优化器
optimizer = StrategyOptimizer(
    data_path='ml_data/BTC-USDT-SWAP_features.csv',
    model_path='ml_models/lgb_model.txt'
)

# 定义参数范围
param_ranges = {
    'stop_loss': (0.01, 0.05),      # 1%-5%
    'take_profit': (0.02, 0.08),    # 2%-8%
    'position_size': (50.0, 500.0), # $50-$500
    'leverage': (5.0, 20.0)         # 5x-20x
}

# 运行优化
best_params = optimizer.bayesian_optimization(
    param_ranges,
    n_iter=50,
    metric='sharpe_ratio'
)

print(f"最优参数: {best_params}")

# 导出结果
optimizer.export_results('optimization_results.json')
```

### 优化结果

优化器会生成两个文件：
- `optimization_results.json` - 详细结果（JSON格式）
- `optimization_results.csv` - 汇总表格（CSV格式）

结果包含：
- 所有测试的参数组合
- 每组参数的表现指标
- 最优参数组合
- 时间戳和测试总数

---

## 🛡️ 4. 动态风险管理系统

### 功能特性

- ✅ **Kelly准则** - 最优仓位计算
- ✅ **VaR/CVaR** - 风险价值度量
- ✅ **动态止损止盈** - 基于ATR
- ✅ **风险限制** - 多维度约束
- ✅ **自动停止** - 触发限制时禁止交易
- ✅ **风险报告** - 详细的风险分析

### Kelly准则仓位计算

```python
from risk_manager import RiskManager

risk_mgr = RiskManager(initial_capital=10000)

# 计算Kelly仓位
# 假设：胜率60%，平均盈利$100，平均亏损$50
position_size = risk_mgr.kelly_position_size(
    win_rate=0.60,
    avg_win=100,
    avg_loss=50,
    max_kelly_fraction=0.25  # 使用25% Kelly（保守）
)
# 输出: Kelly仓位比例约20%
```

### VaR风险度量

```python
# 计算95%置信度下的VaR
var_95 = risk_mgr.calculate_var(confidence_level=0.95, horizon_days=1)
print(f"95% VaR: ${var_95:.2f}")
# 解释：有95%的概率，日亏损不会超过 $var_95

# 计算CVaR（条件风险价值）
cvar_95 = risk_mgr.calculate_cvar(confidence_level=0.95)
print(f"95% CVaR: ${cvar_95:.2f}")
# 解释：在最坏的5%情况下，平均亏损为 $cvar_95
```

### 动态止损止盈

```python
# 基于ATR的止损
entry_price = 50000
atr = 500  # Average True Range

stop_loss = risk_mgr.suggest_stop_loss(
    entry_price=entry_price,
    side='long',
    atr=atr
)
# 止损 = 入场价 - 2×ATR = 49000

take_profit = risk_mgr.suggest_take_profit(
    entry_price=entry_price,
    side='long',
    risk_reward_ratio=2.5,
    atr=atr
)
# 止盈 = 入场价 + 2.5×止损距离 = 52500
```

### 风险限制配置

```python
from risk_manager import RiskLimits

limits = RiskLimits(
    max_daily_loss=500.0,           # 最大日亏损$500
    max_drawdown_pct=0.15,          # 最大回撤15%
    max_position_size=1000.0,       # 单笔最大$1000
    max_total_exposure=5000.0,      # 总暴露$5000
    max_leverage=10.0,              # 最大10倍杠杆
    var_limit=300.0,                # VaR限制$300
    concentration_limit=0.3         # 单品种最多30%
)

risk_mgr = RiskManager(initial_capital=10000, limits=limits)
```

### 风险检查

```python
# 检查是否允许交易
is_allowed, warnings = risk_mgr.check_risk_limits()

if is_allowed:
    print("✅ 允许交易")
else:
    print("🛑 禁止交易")
    for warning in warnings:
        print(f"  {warning}")

# 输出示例：
# 🛑 禁止交易
#   🔴 触发日亏损限制: $-520.00 < -$500
#   🟠 VaR超限: $350.00 > $300.00
```

### 集成到策略

```python
from risk_manager import RiskManager

# 初始化
risk_mgr = RiskManager(initial_capital=10000)

# 交易前检查
is_allowed, warnings = risk_mgr.check_risk_limits()
if not is_allowed:
    print("风险限制触发，停止交易")
    return

# 计算仓位
position_size = risk_mgr.calculate_position_size(
    signal_strength=0.8,  # 信号强度
    volatility=0.02       # 预期波动率
)

# 开仓
risk_mgr.update_position('BTC-USDT-SWAP', 0.1, 50000, 'long')

# 平仓时更新
risk_mgr.close_position('BTC-USDT-SWAP', 51000, pnl=100)

# 导出风险报告
risk_mgr.export_risk_report('risk_report.txt')
```

---

## 📦 5. 多策略组合系统

### 功能特性

- ✅ **策略注册** - 灵活的策略管理
- ✅ **动态分配** - 4种分配方法
- ✅ **相关性分析** - 策略间相关性矩阵
- ✅ **自动再平衡** - 定期优化分配
- ✅ **组合优化** - 最大化夏普比率

### 分配方法对比

| 方法 | 原理 | 优点 | 缺点 |
|------|------|------|------|
| 等权重 | 平均分配 | 简单、多样化 | 忽略表现差异 |
| 基于表现 | 根据夏普+收益 | 奖励优秀策略 | 可能过度集中 |
| 风险平价 | 等风险贡献 | 风险分散 | 可能低收益 |
| **最大夏普** | 优化夏普比率 | **最优风险收益** | **推荐** |

### 快速开始

```python
from portfolio_manager import PortfolioManager

# 创建组合管理器
portfolio = PortfolioManager(total_capital=10000)

# 添加策略
portfolio.add_strategy(
    name='ML策略',
    strategy_type='ml',
    initial_allocation=0.35,  # 初始35%
    min_allocation=0.10,      # 最少10%
    max_allocation=0.50       # 最多50%
)

portfolio.add_strategy('订单簿策略', 'orderbook', 0.35)
portfolio.add_strategy('趋势策略', 'trend', 0.30)
```

### 更新策略表现

```python
# 运行回测后更新
from advanced_backtest import backtest_from_ml_data

backtester, result = backtest_from_ml_data(
    data_path='ml_data/BTC-USDT-SWAP_features.csv',
    model_path='ml_models/lgb_model.txt',
    config=config
)

# 提取数据
equity_curve = backtester.equity_history
returns = backtester.returns_history
trades = backtester.trades

# 更新组合管理器
portfolio.update_strategy_results(
    name='ML策略',
    equity_curve=equity_curve,
    returns=returns,
    trades_data=trades
)
```

### 再平衡

```python
# 检查是否需要再平衡（默认7天）
if portfolio.should_rebalance():
    # 方法1: 最大化夏普比率（推荐）
    portfolio.allocator.rebalance('sharpe')

    # 方法2: 风险平价
    portfolio.allocator.rebalance('risk_parity')

    # 方法3: 基于表现
    portfolio.allocator.rebalance('performance')

    # 方法4: 等权重
    portfolio.allocator.rebalance('equal')
```

### 组合分析

```python
# 获取组合指标
metrics = portfolio.allocator.get_portfolio_metrics()
print(f"组合收益率: {metrics['portfolio_return']:.2%}")
print(f"组合夏普: {metrics['portfolio_sharpe']:.3f}")
print(f"最大回撤: {metrics['max_drawdown']:.2%}")

# 相关性分析
corr_matrix = portfolio.allocator.calculate_correlation_matrix()
print(corr_matrix)
# 输出示例:
#             ML策略  订单簿策略  趋势策略
# ML策略       1.00    0.35    0.42
# 订单簿策略   0.35    1.00    0.28
# 趋势策略     0.42    0.28    1.00

# 导出报告
portfolio.export_report('portfolio_report.txt')
```

### 实战示例

```python
# 完整的多策略系统
import time
from portfolio_manager import PortfolioManager
from risk_manager import RiskManager

# 初始化
portfolio = PortfolioManager(total_capital=10000)
risk_mgr = RiskManager(initial_capital=10000)

# 注册策略
strategies = {
    'ML策略': {'type': 'ml', 'allocation': 0.35},
    '订单簿策略': {'type': 'orderbook', 'allocation': 0.35},
    '趋势策略': {'type': 'trend', 'allocation': 0.30}
}

for name, config in strategies.items():
    portfolio.add_strategy(name, config['type'], config['allocation'])

# 主循环
while True:
    # 1. 检查风险
    is_allowed, warnings = risk_mgr.check_risk_limits()
    if not is_allowed:
        print("⚠️ 风险限制触发，暂停交易")
        time.sleep(3600)  # 等待1小时
        continue

    # 2. 运行各策略（伪代码）
    for strategy_name in strategies:
        allocation = portfolio.get_strategy_allocation(strategy_name)
        # 使用分配的资金运行策略
        run_strategy(strategy_name, capital=allocation)

    # 3. 每天再平衡
    portfolio.rebalance_if_needed('sharpe')

    # 4. 导出报告
    if time.time() % 86400 == 0:  # 每天
        portfolio.export_report()
        risk_mgr.export_risk_report()

    time.sleep(60)  # 每分钟检查一次
```

---

## 🐳 6. Docker容器化部署

### 功能特性

- ✅ 完整的Docker镜像
- ✅ docker-compose多服务编排
- ✅ 服务包括：交易bot、Redis、PostgreSQL、Grafana、Prometheus
- ✅ 自动重启和健康检查
- ✅ 数据持久化
- ✅ 网络隔离

### 快速启动

```bash
# 1. 配置环境变量
cp .env.example .env
# 编辑.env，填入你的API密钥

# 2. 启动基础服务
docker-compose up -d trading-bot redis

# 3. 启动所有策略（生产环境）
docker-compose --profile production up -d

# 4. 启动监控套件
docker-compose --profile production --profile monitoring up -d
```

### 服务访问

| 服务 | 端口 | 访问地址 |
|------|------|----------|
| 监控面板 | 8501 | http://localhost:8501 |
| Grafana | 3000 | http://localhost:3000 |
| Prometheus | 9090 | http://localhost:9090 |
| Redis | 6379 | localhost:6379 |
| PostgreSQL | 5432 | localhost:5432 |

### 常用命令

```bash
# 查看日志
docker-compose logs -f trading-bot

# 重启服务
docker-compose restart trading-bot

# 停止所有服务
docker-compose down

# 进入容器
docker-compose exec trading-bot bash

# 查看资源使用
docker stats
```

详细部署文档：[DOCKER_DEPLOYMENT.md](DOCKER_DEPLOYMENT.md)

---

## 📚 完整工作流

### 1. 数据收集

```bash
# 启动WebSocket数据收集
python websocket_stream.py &

# 或使用ML策略的数据收集模式
python zhen_ml.py --mode collect --hours 12
```

### 2. 模型训练

```bash
# 训练机器学习模型
python zhen_ml.py --mode train
```

### 3. 参数优化

```bash
# 优化策略参数
python strategy_optimizer.py \
  --data ml_data/BTC-USDT-SWAP_features.csv \
  --model ml_models/lgb_model.txt \
  --method bayesian \
  --iterations 50
```

### 4. 回测验证

```bash
# 使用优化后的参数回测
python backtest_ml.py

# 可视化回测结果
python visualize_backtest.py \
  --equity backtest_equity.csv \
  --trades backtest_trades.csv \
  --output backtest_report.png
```

### 5. 实盘运行

```python
# 集成所有工具的实盘策略
from websocket_stream import OKXWebSocket
from risk_manager import RiskManager
from portfolio_manager import PortfolioManager

# 初始化
ws = OKXWebSocket()
risk_mgr = RiskManager(initial_capital=10000)
portfolio = PortfolioManager(total_capital=10000)

# 注册策略并运行
portfolio.add_strategy('ML策略', 'ml', 0.50)
portfolio.add_strategy('订单簿策略', 'orderbook', 0.50)

# 主循环
while True:
    # 风险检查
    if not risk_mgr.check_risk_limits()[0]:
        continue

    # 获取实时数据
    orderbook = ws.get_orderbook('BTC-USDT-SWAP')

    # 运行策略逻辑
    # ...

    # 再平衡
    portfolio.rebalance_if_needed('sharpe')
```

### 6. 监控运维

```bash
# 启动监控面板
streamlit run monitor_dashboard.py

# 或使用Docker
docker-compose up -d trading-bot
```

---

## 🎓 最佳实践

### 1. 参数优化

- **首次优化**：使用贝叶斯优化，迭代50-100次
- **定期调参**：每月重新优化一次
- **验证**：使用walk-forward analysis验证稳定性

### 2. 风险管理

- **Kelly仓位**：使用25%-50%的Kelly值（保守）
- **VaR监控**：每日检查95% VaR
- **止损止盈**：使用2倍ATR作为止损，2-3倍风险收益比

### 3. 组合管理

- **策略数量**：3-5个低相关性策略
- **再平衡频率**：每周一次
- **分配方法**：优先使用最大夏普比率

### 4. 监控运维

- **实时监控**：使用Streamlit面板
- **日志记录**：保留至少30天的日志
- **备份**：每日备份模型和配置

### 5. Docker部署

- **开发环境**：仅运行trading-bot和redis
- **生产环境**：启用所有策略和监控
- **资源限制**：设置内存和CPU限制
- **数据持久化**：使用卷挂载重要数据

---

## ⚠️ 注意事项

1. **实盘前测试**
   - 充分回测（至少6个月历史数据）
   - 参数优化避免过拟合
   - 小资金测试（1-5%总资金）

2. **风险控制**
   - 严格遵守风险限制
   - 不要频繁调整参数
   - 保持冷静，避免情绪化交易

3. **性能优化**
   - WebSocket降低延迟
   - Redis缓存减少API调用
   - 异步处理提高并发

4. **安全性**
   - 不要将API密钥提交到Git
   - 使用环境变量管理敏感信息
   - 定期更新密码

5. **合规性**
   - 遵守交易所规则
   - 注意API频率限制
   - 了解当地法律法规

---

## 📞 支持与反馈

- **问题反馈**：提交GitHub Issue
- **功能建议**：欢迎Pull Request
- **技术交流**：加入社区讨论

---

## 📄 相关文档

- [快速开始指南](QUICK_START.md)
- [高级工具说明](ADVANCED_TOOLS.md)
- [Docker部署指南](DOCKER_DEPLOYMENT.md)
- [ML策略文档](ML_STRATEGY.md)
- [订单簿策略文档](ORDERBOOK_STRATEGY.md)

---

**最后更新**: 2025-01-20
**版本**: v2.0
**作者**: Jiezhen Trading Team
