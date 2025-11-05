"""
配置管理模块
提供配置加载、验证和访问功能
"""
import json
from typing import Dict, Any, List
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TradingPairConfig:
    """单个交易对的配置"""
    inst_id: str
    long_amount_usdt: float
    short_amount_usdt: float
    value_multiplier: float = 2.0
    ema_period: int = 240
    ema_enabled: bool = True

    def __post_init__(self):
        """配置后验证"""
        if self.ema_period == 0:
            self.ema_enabled = False

    def validate(self) -> List[str]:
        """
        验证配置参数

        Returns:
            错误信息列表（如果为空则表示验证通过）
        """
        errors = []

        if self.long_amount_usdt <= 0:
            errors.append(f"{self.inst_id}: long_amount_usdt必须大于0")

        if self.short_amount_usdt <= 0:
            errors.append(f"{self.inst_id}: short_amount_usdt必须大于0")

        if self.value_multiplier <= 0:
            errors.append(f"{self.inst_id}: value_multiplier必须大于0")

        if self.value_multiplier > 10:
            errors.append(f"{self.inst_id}: value_multiplier不建议超过10（当前: {self.value_multiplier}）")

        if self.ema_period < 0:
            errors.append(f"{self.inst_id}: ema必须大于等于0")

        if self.ema_period > 0 and self.ema_period < 10:
            errors.append(f"{self.inst_id}: ema周期太小，建议至少10（当前: {self.ema_period}）")

        return errors


@dataclass
class OKXConfig:
    """OKX API配置"""
    api_key: str
    secret: str
    password: str
    simulated: bool = False

    def validate(self) -> List[str]:
        """验证OKX配置"""
        errors = []

        if not self.api_key:
            errors.append("OKX API Key不能为空")

        if not self.secret:
            errors.append("OKX Secret不能为空")

        if not self.password:
            errors.append("OKX Password不能为空")

        return errors


@dataclass
class RiskConfig:
    """风险控制配置"""
    max_position_size_usdt: float = 1000.0  # 单个交易对最大持仓（USDT）
    max_total_position_usdt: float = 5000.0  # 总持仓限制（USDT）
    max_daily_loss_usdt: float = 500.0  # 单日最大亏损
    max_orders_per_pair: int = 2  # 每个交易对最大挂单数
    enable_risk_control: bool = True  # 是否启用风险控制

    def validate(self) -> List[str]:
        """验证风险控制配置"""
        errors = []

        if self.max_position_size_usdt <= 0:
            errors.append("max_position_size_usdt必须大于0")

        if self.max_total_position_usdt <= 0:
            errors.append("max_total_position_usdt必须大于0")

        if self.max_daily_loss_usdt <= 0:
            errors.append("max_daily_loss_usdt必须大于0")

        if self.max_orders_per_pair <= 0:
            errors.append("max_orders_per_pair必须大于0")

        return errors


@dataclass
class Config:
    """完整的应用配置"""
    okx: OKXConfig
    trading_pairs: Dict[str, TradingPairConfig] = field(default_factory=dict)
    monitor_interval: int = 60
    leverage: int = 10
    feishu_webhook: str = ""
    risk: RiskConfig = field(default_factory=RiskConfig)
    batch_size: int = 5
    cache_ttl: int = 60

    def validate(self) -> List[str]:
        """
        验证所有配置

        Returns:
            错误信息列表
        """
        errors = []

        # 验证OKX配置
        errors.extend(self.okx.validate())

        # 验证风险控制配置
        errors.extend(self.risk.validate())

        # 验证交易对配置
        if not self.trading_pairs:
            errors.append("至少需要配置一个交易对")

        for pair_config in self.trading_pairs.values():
            errors.extend(pair_config.validate())

        # 验证其他参数
        if self.monitor_interval < 10:
            errors.append("monitor_interval不建议小于10秒")

        if self.leverage < 1 or self.leverage > 125:
            errors.append("leverage必须在1-125之间")

        if self.batch_size < 1 or self.batch_size > 20:
            errors.append("batch_size建议在1-20之间")

        if self.cache_ttl < 1:
            errors.append("cache_ttl必须大于0")

        return errors

    def get_pair_config(self, inst_id: str) -> TradingPairConfig | None:
        """获取指定交易对的配置"""
        return self.trading_pairs.get(inst_id)

    def get_all_inst_ids(self) -> List[str]:
        """获取所有交易对ID"""
        return list(self.trading_pairs.keys())


class ConfigManager:
    """配置管理器"""

    def __init__(self, config_path: str = "config.json"):
        """
        初始化配置管理器

        Args:
            config_path: 配置文件路径
        """
        self.config_path = Path(config_path)
        self.config: Config | None = None

    def load_config(self) -> Config:
        """
        加载并验证配置文件

        Returns:
            配置对象

        Raises:
            FileNotFoundError: 配置文件不存在
            json.JSONDecodeError: JSON格式错误
            ValueError: 配置验证失败
        """
        if not self.config_path.exists():
            raise FileNotFoundError(f"配置文件不存在: {self.config_path}")

        with open(self.config_path, 'r', encoding='utf-8') as f:
            raw_config = json.load(f)

        self.config = self._parse_config(raw_config)

        # 验证配置
        errors = self.config.validate()
        if errors:
            error_msg = "配置验证失败:\n" + "\n".join(f"  - {err}" for err in errors)
            raise ValueError(error_msg)

        return self.config

    def _parse_config(self, raw_config: Dict[str, Any]) -> Config:
        """
        解析原始配置字典为配置对象

        Args:
            raw_config: 原始配置字典

        Returns:
            配置对象
        """
        # 解析OKX配置
        okx_raw = raw_config.get('okx', {})
        okx_config = OKXConfig(
            api_key=okx_raw.get('apiKey', ''),
            secret=okx_raw.get('secret', ''),
            password=okx_raw.get('password', ''),
            simulated=okx_raw.get('simulated', False)
        )

        # 解析交易对配置
        trading_pairs = {}
        trading_pairs_raw = raw_config.get('tradingPairs', {})
        for inst_id, pair_raw in trading_pairs_raw.items():
            trading_pairs[inst_id] = TradingPairConfig(
                inst_id=inst_id,
                long_amount_usdt=pair_raw.get('long_amount_usdt', 20),
                short_amount_usdt=pair_raw.get('short_amount_usdt', 20),
                value_multiplier=pair_raw.get('value_multiplier', 2.0),
                ema_period=pair_raw.get('ema', 240)
            )

        # 解析风险控制配置
        risk_raw = raw_config.get('risk', {})
        risk_config = RiskConfig(
            max_position_size_usdt=risk_raw.get('max_position_size_usdt', 1000.0),
            max_total_position_usdt=risk_raw.get('max_total_position_usdt', 5000.0),
            max_daily_loss_usdt=risk_raw.get('max_daily_loss_usdt', 500.0),
            max_orders_per_pair=risk_raw.get('max_orders_per_pair', 2),
            enable_risk_control=risk_raw.get('enable_risk_control', True)
        )

        return Config(
            okx=okx_config,
            trading_pairs=trading_pairs,
            monitor_interval=raw_config.get('monitor_interval', 60),
            leverage=raw_config.get('leverage', 10),
            feishu_webhook=raw_config.get('feishu_webhook', ''),
            risk=risk_config,
            batch_size=raw_config.get('batch_size', 5),
            cache_ttl=raw_config.get('cache_ttl', 60)
        )

    def get_config(self) -> Config:
        """
        获取配置对象（如果未加载则自动加载）

        Returns:
            配置对象
        """
        if self.config is None:
            self.config = self.load_config()
        return self.config

    def reload_config(self) -> Config:
        """
        重新加载配置文件

        Returns:
            配置对象
        """
        return self.load_config()

    def save_example_config(self, path: str = "config.example.json"):
        """
        保存示例配置文件

        Args:
            path: 保存路径
        """
        example_config = {
            "okx": {
                "apiKey": "YOUR_API_KEY",
                "secret": "YOUR_SECRET",
                "password": "YOUR_PASSWORD",
                "simulated": False
            },
            "feishu_webhook": "https://open.feishu.cn/open-apis/bot/v2/hook/xxx",
            "monitor_interval": 60,
            "leverage": 10,
            "batch_size": 5,
            "cache_ttl": 60,
            "risk": {
                "max_position_size_usdt": 1000.0,
                "max_total_position_usdt": 5000.0,
                "max_daily_loss_usdt": 500.0,
                "max_orders_per_pair": 2,
                "enable_risk_control": True
            },
            "tradingPairs": {
                "BTC-USDT-SWAP": {
                    "long_amount_usdt": 20,
                    "short_amount_usdt": 20,
                    "value_multiplier": 2,
                    "ema": 240
                },
                "ETH-USDT-SWAP": {
                    "long_amount_usdt": 20,
                    "short_amount_usdt": 20,
                    "value_multiplier": 2,
                    "ema": 240
                }
            }
        }

        with open(path, 'w', encoding='utf-8') as f:
            json.dump(example_config, f, indent=4, ensure_ascii=False)
