"""配置测试"""
import os
import tempfile
import pytest
from pathlib import Path

from openscaw.config import ConfigManager, DEFAULT_CONFIG


class TestConfigManager:
    def test_default_config_creation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yaml"
            config = ConfigManager(str(config_path))
            
            assert config_path.exists()
            assert config.config is not None
    
    def test_monitor_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yaml"
            config = ConfigManager(str(config_path))
            
            monitor_cfg = config.get_monitor_config()
            assert monitor_cfg.check_interval == 30
            assert monitor_cfg.max_context_tokens == 8000
    
    def test_get_apis(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yaml"
            config = ConfigManager(str(config_path))
            
            apis = config.get_apis()
            assert len(apis) == 3  # kimi, deepseek, minimax
            
            # 检查 API 名称
            api_names = [api.name for api in apis]
            assert "kimi" in api_names
            assert "deepseek" in api_names
            assert "minimax" in api_names


class TestDefaultConfig:
    def test_has_required_sections(self):
        assert "monitor" in DEFAULT_CONFIG
        assert "apis" in DEFAULT_CONFIG
        assert "fix_strategies" in DEFAULT_CONFIG
        assert "notifications" in DEFAULT_CONFIG
    
    def test_api_configs(self):
        apis = DEFAULT_CONFIG["apis"]
        assert "kimi" in apis
        assert "deepseek" in apis
        assert "minimax" in apis
        
        for api_name, api_config in apis.items():
            assert "base_url" in api_config
            assert "env_key" in api_config
            assert "models" in api_config
