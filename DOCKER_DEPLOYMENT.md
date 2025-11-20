# Docker 部署指南

本指南介绍如何使用Docker容器化部署量化交易系统。

## 📋 前置要求

- Docker >= 20.10
- Docker Compose >= 2.0
- 至少 2GB 可用内存
- 至少 5GB 可用磁盘空间

## 🚀 快速开始

### 1. 配置环境变量

复制环境变量示例文件：

```bash
cp .env.example .env
```

编辑 `.env` 文件，填入您的OKX API配置：

```bash
OKX_API_KEY=your_api_key_here
OKX_SECRET_KEY=your_secret_key_here
OKX_PASSPHRASE=your_passphrase_here
```

### 2. 启动基础服务

启动监控面板和Redis：

```bash
docker-compose up -d trading-bot redis
```

访问监控面板：http://localhost:8501

### 3. 启动生产环境（包含所有策略）

```bash
docker-compose --profile production up -d
```

这将启动：
- ✅ 监控面板 (端口 8501)
- ✅ ML策略
- ✅ 订单簿策略
- ✅ Redis缓存

### 4. 启动完整监控套件

包含Grafana和Prometheus：

```bash
docker-compose --profile production --profile monitoring up -d
```

访问：
- 监控面板: http://localhost:8501
- Grafana: http://localhost:3000 (admin/admin)
- Prometheus: http://localhost:9090

### 5. 启动数据库服务

如需PostgreSQL数据库：

```bash
docker-compose --profile database up -d
```

## 📊 服务说明

### trading-bot
- **功能**: Streamlit实时监控面板
- **端口**: 8501
- **状态**: 默认启动

### ml-strategy
- **功能**: 机器学习交易策略
- **配置**: profile: production
- **依赖**: Redis

### orderbook-strategy
- **功能**: 订单簿分析策略
- **配置**: profile: production
- **依赖**: Redis

### redis
- **功能**: 数据缓存和策略间通信
- **端口**: 6379
- **配置**: 最大内存256MB, LRU淘汰策略

### postgres (可选)
- **功能**: 历史数据存储
- **端口**: 5432
- **配置**: profile: database

### grafana (可选)
- **功能**: 高级可视化监控
- **端口**: 3000
- **配置**: profile: monitoring

### prometheus (可选)
- **功能**: 指标收集
- **端口**: 9090
- **配置**: profile: monitoring

## 🔧 常用命令

### 查看服务状态

```bash
docker-compose ps
```

### 查看日志

```bash
# 查看所有服务日志
docker-compose logs -f

# 查看特定服务日志
docker-compose logs -f trading-bot
docker-compose logs -f ml-strategy
```

### 停止服务

```bash
# 停止所有服务
docker-compose down

# 停止并删除数据卷
docker-compose down -v
```

### 重启服务

```bash
# 重启特定服务
docker-compose restart trading-bot

# 重启所有服务
docker-compose restart
```

### 进入容器

```bash
# 进入交易机器人容器
docker-compose exec trading-bot bash

# 进入Redis容器
docker-compose exec redis redis-cli
```

### 更新代码

```bash
# 拉取最新代码
git pull

# 重新构建并启动
docker-compose up -d --build
```

## 📈 监控和维护

### 健康检查

所有服务都配置了健康检查：

```bash
docker-compose ps
```

查看 `STATUS` 列，应该显示 `Up (healthy)`。

### 查看资源使用

```bash
docker stats
```

### 备份数据

```bash
# 备份Redis数据
docker-compose exec redis redis-cli SAVE
docker cp jiezhen-redis:/data/dump.rdb ./backup/redis_backup.rdb

# 备份PostgreSQL数据
docker-compose exec postgres pg_dump -U trader trading > ./backup/postgres_backup.sql

# 备份模型和日志
tar -czf backup/ml_backup_$(date +%Y%m%d).tar.gz ml_data/ ml_models/ log/
```

### 恢复数据

```bash
# 恢复Redis数据
docker cp ./backup/redis_backup.rdb jiezhen-redis:/data/dump.rdb
docker-compose restart redis

# 恢复PostgreSQL数据
cat ./backup/postgres_backup.sql | docker-compose exec -T postgres psql -U trader trading
```

## 🔒 安全建议

1. **不要将 `.env` 文件提交到Git**
   ```bash
   echo ".env" >> .gitignore
   ```

2. **定期更新密码**
   - 更改Grafana默认密码
   - 更改PostgreSQL密码
   - 定期轮换API密钥

3. **限制网络访问**
   - 使用防火墙限制端口访问
   - 生产环境建议使用反向代理（Nginx）
   - 启用HTTPS

4. **资源限制**

   在 `docker-compose.yml` 中添加资源限制：
   ```yaml
   services:
     trading-bot:
       deploy:
         resources:
           limits:
             cpus: '1.0'
             memory: 1G
   ```

## 🐛 故障排查

### 服务无法启动

```bash
# 查看详细错误日志
docker-compose logs trading-bot

# 检查端口占用
netstat -tuln | grep 8501

# 清理并重启
docker-compose down -v
docker-compose up -d --build
```

### Redis连接失败

```bash
# 测试Redis连接
docker-compose exec redis redis-cli ping

# 检查Redis日志
docker-compose logs redis
```

### 内存不足

```bash
# 清理未使用的Docker资源
docker system prune -a

# 查看卷占用
docker system df -v
```

### API请求失败

1. 检查 `.env` 文件中的API配置
2. 确认API密钥权限
3. 检查网络连接
4. 查看策略日志

## 🌐 生产部署建议

### 1. 使用Docker Swarm或Kubernetes

对于多节点部署，建议使用编排工具：

```bash
# Docker Swarm
docker swarm init
docker stack deploy -c docker-compose.yml trading
```

### 2. 配置反向代理

使用Nginx作为反向代理：

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }
}
```

### 3. 设置自动重启

编辑 `/etc/systemd/system/docker-compose-trading.service`:

```ini
[Unit]
Description=Trading Bot
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/path/to/jiezhen
ExecStart=/usr/local/bin/docker-compose up -d
ExecStop=/usr/local/bin/docker-compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
```

启用自动重启：
```bash
sudo systemctl enable docker-compose-trading
sudo systemctl start docker-compose-trading
```

### 4. 日志管理

配置日志轮转：

```yaml
services:
  trading-bot:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

### 5. 监控告警

集成Prometheus AlertManager：

```yaml
# prometheus.yml
alerting:
  alertmanagers:
    - static_configs:
        - targets:
          - alertmanager:9093

rule_files:
  - 'alerts.yml'
```

## 📚 更多资源

- [Docker官方文档](https://docs.docker.com/)
- [Docker Compose文档](https://docs.docker.com/compose/)
- [Streamlit部署指南](https://docs.streamlit.io/knowledge-base/deploy)
- [OKX API文档](https://www.okx.com/docs-v5/)

## ⚠️ 免责声明

本系统仅供学习和研究使用。量化交易存在风险，请谨慎使用实盘资金。使用者需自行承担所有交易风险和损失。

---

**最后更新**: 2025-01-20
**维护者**: Jiezhen Trading Team
