"""监控测试"""
import pytest
from datetime import datetime
from unittest.mock import Mock, patch

from openscaw.monitor import OpenClawMonitor, HealthLevel, HealthReport, ProcessInfo


class TestOpenClawMonitor:
    @pytest.fixture
    def monitor(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yaml"
            from openscaw.config import ConfigManager
            config = ConfigManager(str(config_path))
            return OpenClawMonitor(config)
    
    def test_init(self, monitor):
        assert monitor.config is not None
        assert monitor.monitor_cfg is not None
        assert monitor.api_manager is not None
    
    def test_evaluate_health_healthy(self, monitor):
        process = Mock()
        process.memory_mb = 500
        process.cpu_percent = 10
        
        level = monitor._evaluate_health(
            process=process,
            api_status={"kimi": "healthy"},
            context_tokens=1000,
            response_time=500,
            errors=[]
        )
        
        assert level == HealthLevel.HEALTHY
    
    def test_evaluate_health_critical_no_process(self, monitor):
        level = monitor._evaluate_health(
            process=None,
            api_status={},
            context_tokens=0,
            response_time=0,
            errors=[]
        )
        
        assert level == HealthLevel.CRITICAL
    
    def test_evaluate_health_warning_context(self, monitor):
        process = Mock()
        process.memory_mb = 500
        process.cpu_percent = 10
        
        level = monitor._evaluate_health(
            process=process,
            api_status={"kimi": "healthy"},
            context_tokens=7500,  # 超过80%阈值
            response_time=500,
            errors=[]
        )
        
        assert level == HealthLevel.WARNING
    
    def test_generate_suggestions(self, monitor):
        process = Mock()
        process.memory_mb = 3000
        process.cpu_percent = 10
        
        suggestions = monitor._generate_suggestions(
            level=HealthLevel.WARNING,
            process=process,
            api_status={"kimi": "healthy"},
            context_tokens=7500,
            response_time=15000,
            errors=["some error"]
        )
        
        assert len(suggestions) > 0
        assert any("上下文" in s for s in suggestions)


import tempfile
from pathlib import Path
