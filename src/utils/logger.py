"""
日志管理模块
提供统一的日志记录功能
"""
import logging
import os
from logging.handlers import TimedRotatingFileHandler


class Logger:
    """日志管理器类"""

    _instances = {}

    @classmethod
    def get_logger(cls, name: str = __name__, log_file: str = "log/okx.log") -> logging.Logger:
        """
        获取日志记录器（单例模式）

        Args:
            name: 日志记录器名称
            log_file: 日志文件路径

        Returns:
            日志记录器对象
        """
        if name in cls._instances:
            return cls._instances[name]

        logger = logging.getLogger(name)
        logger.setLevel(logging.INFO)

        # 清除已有的处理器
        logger.handlers.clear()

        # 确保日志目录存在
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)

        # 文件处理器 - 按天轮转
        file_handler = TimedRotatingFileHandler(
            log_file,
            when='midnight',
            interval=1,
            backupCount=7,
            encoding='utf-8'
        )
        file_handler.suffix = "%Y-%m-%d"

        # 控制台处理器
        console_handler = logging.StreamHandler()

        # 设置格式
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)

        # 添加处理器
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

        cls._instances[name] = logger
        return logger
