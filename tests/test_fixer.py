"""自动修复测试"""
import pytest
from unittest.mock import Mock, patch, AsyncMock

from openscaw.fixer import AutoFixer, FixResult
from openscaw.monitor import HealthLevel, HealthReport


class TestAutoFixer:
    @pytest.fixture
    def fixer(self):
        from openscaw.config import ConfigManager
        with tempfile.TemporaryDirectory() as tmpdir:
            config = ConfigManager(Path(tmpdir) / "config.yaml")
            return AutoFixer(config=config)
    
    @pytest.mark.asyncio
    async def test_fix_unknown_issue(self, fixer):
        result = await fixer.fix("unknown_issue")
        assert result == FixResult.FAILED
    
    @pytest.mark.asyncio
    async def test_fix_with_max_retries(self, fixer):
        # 设置连续失败
        fixer._consecutive_failures["test_issue"] = 10
        
        # 添加一个测试动作
        fixer.actions["test_issue"] = Mock()
        fixer.actions["test_issue"].auto_enabled = True
        fixer.strategies["test_issue"] = {"enabled": True, "max_retries": 3}
        
        result = await fixer.fix("test_issue")
        assert result == FixResult.MANUAL_REQUIRED


import tempfile
from pathlib import Path
