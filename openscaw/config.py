"""配置管理"""
import os
import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Union

DEFAULT_CONFIG = {
    "monitor": {
        "check_interval": 30,
        "max_context_tokens": 8000,
        "response_timeout": 10,
        "memory_threshold_mb": 2048,
        "cpu_threshold_percent": 80
    },
    "apis": {
        "kimi": {
            "base_url": "https://api.moonshot.cn/v1",
            "env_key": "KIMI_API_KEY",
            "models": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"]
        },
        "deepseek": {
            "base_url": "https://api.deepseek.com/v1",
            "env_key": "DEEPSEEK_API_KEY", 
            "models": ["deepseek-chat", "deepseek-reasoner"]
        },
        "minimax": {
            "base_url": "https://api.minimax.chat/v1",
            "env_key": "MINIMAX_API_KEY",
            "models": ["abab6.5-chat", "abab6.5s-chat"]
        }
    },
    "fix_strategies": {
        "context_overflow": {
            "enabled": True,
            "action": "compress_context",
            "threshold": 7000
        },
        "api_key_invalid": {
            "enabled": True,
            "action": "switch_api_key",
            "max_retries": 3
        },
        "process_stuck": {
            "enabled": True,
            "action": "restart_process",
            "graceful_timeout": 5
        },
        "no_response": {
            "enabled": True,
            "action": "ping_wakeup",
            "ping_timeout": 3
        }
    },
    "notifications": {
        "enabled": True,
        "channels": ["console"],
        "webhook_url": None,
        "notify_on": ["critical", "fix_failed"]
    },
    "logging": {
        "level": "INFO",
        "file": "~/.openscaw/openscaw.log",
        "max_size_mb": 100,
        "backup_count": 5
    }
}

@dataclass
class APIConfig:
    name: str
    base_url: str
    api_key: str
    models: List[str]
    current_model: str = ""
    is_active: bool = True

@dataclass 
class MonitorConfig:
    check_interval: int = 30
    max_context_tokens: int = 8000
    response_timeout: int = 10
    memory_threshold_mb: int = 2048
    cpu_threshold_percent: int = 80
    target_process_name: str = "openclaw"

class ConfigManager:
    def __init__(self, config_path: Union[str, Path, None] = None):
        self.config_dir = Path.home() / ".openscaw"
        self.config_dir.mkdir(exist_ok=True)
        
        if config_path is None:
            self.config_path = self.config_dir / "config.yaml"
        else:
            self.config_path = Path(config_path)
        
        self.config = self._load_or_create()
        
    def _load_or_create(self) -> dict:
        if self.config_path.exists():
            with open(self.config_path, 'r', encoding='utf-8') as f:
                user_config = yaml.safe_load(f)
                # 合并默认配置
                config = DEFAULT_CONFIG.copy()
                self._deep_update(config, user_config)
                return config
        else:
            self._create_default_config()
            return DEFAULT_CONFIG.copy()
    
    def _create_default_config(self):
        with open(self.config_path, 'w', encoding='utf-8') as f:
            yaml.dump(DEFAULT_CONFIG, f, allow_unicode=True, sort_keys=False)
        print(f"✓ 已创建默认配置: {self.config_path}")
    
    def _deep_update(self, base: dict, update: dict):
        for key, value in update.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_update(base[key], value)
            else:
                base[key] = value
    
    def get_apis(self) -> List[APIConfig]:
        """获取所有配置的API"""
        apis = []
        for name, cfg in self.config["apis"].items():
            api_key = os.getenv(cfg["env_key"], "")
            apis.append(APIConfig(
                name=name,
                base_url=cfg["base_url"],
                api_key=api_key,
                models=cfg.get("models", []),
                current_model=cfg.get("models", [""])[0],
                is_active=bool(api_key)
            ))
        return apis
    
    def get_active_api(self) -> Optional[APIConfig]:
        """获取第一个可用的API"""
        for api in self.get_apis():
            if api.is_active:
                return api
        return None
    
    def get_monitor_config(self) -> MonitorConfig:
        m = self.config["monitor"]
        return MonitorConfig(
            check_interval=m.get("check_interval", 30),
            max_context_tokens=m.get("max_context_tokens", 8000),
            response_timeout=m.get("response_timeout", 10),
            memory_threshold_mb=m.get("memory_threshold_mb", 2048),
            cpu_threshold_percent=m.get("cpu_threshold_percent", 80),
            target_process_name=m.get("target_process_name", "openclaw")
        )
    
    def get_fix_strategies(self) -> dict:
        return self.config.get("fix_strategies", DEFAULT_CONFIG["fix_strategies"])
    
    def save(self):
        with open(self.config_path, 'w', encoding='utf-8') as f:
            yaml.dump(self.config, f, allow_unicode=True, sort_keys=False)
    
    def edit(self):
        """使用默认编辑器打开配置文件"""
        editor = os.getenv('EDITOR', 'nano')
        os.system(f"{editor} {self.config_path}")