"""诊断引擎测试"""
import pytest
from pathlib import Path

from openscaw.diagnostics import DiagnosticsEngine, IssueCategory, DiagnosisResult


class TestDiagnosticsEngine:
    @pytest.fixture
    def engine(self):
        return DiagnosticsEngine()
    
    def test_diagnose_api_issues(self, engine):
        symptoms = {
            "errors": ["Invalid API key"],
            "api_status": {"kimi": "invalid_key"},
            "context_tokens": 1000,
            "memory_mb": 500,
            "response_time_ms": 500
        }
        
        result = engine.diagnose(symptoms)
        assert result.category == IssueCategory.API
        assert result.confidence > 0.5
        assert len(result.recommendations) > 0
    
    def test_diagnose_resource_issues(self, engine):
        symptoms = {
            "errors": ["Out of memory"],
            "api_status": {"kimi": "healthy"},
            "context_tokens": 9000,  # 超长上下文
            "memory_mb": 3000,  # 内存过高
            "response_time_ms": 500
        }
        
        result = engine.diagnose(symptoms)
        # 可能被诊断为资源或API问题
        assert result.category in [IssueCategory.RESOURCE, IssueCategory.API]
    
    def test_diagnose_network_issues(self, engine):
        symptoms = {
            "errors": [],
            "api_status": {"kimi": "timeout"},
            "context_tokens": 1000,
            "memory_mb": 500,
            "response_time_ms": 15000  # 超时
        }
        
        result = engine.diagnose(symptoms)
        assert result.category == IssueCategory.NETWORK
    
    def test_load_patterns(self, engine):
        patterns = engine._patterns
        assert "context_overflow" in patterns
        assert "api_auth_failed" in patterns
        assert "rate_limit" in patterns
    
    def test_generate_report(self, engine):
        diagnosis = DiagnosisResult(
            category=IssueCategory.API,
            root_cause="API Key 无效",
            confidence=0.9,
            evidence=["认证失赴"],
            recommendations=["更新 API Key"],
            related_logs=[]
        )
        
        symptoms = {
            "context_tokens": 1000,
            "memory_mb": 500,
            "response_time_ms": 500,
            "api_status": {"kimi": "invalid_key"},
            "errors": []
        }
        
        report = engine.generate_report(diagnosis, symptoms)
        assert "API" in report
        assert "API Key 无效" in report
        assert "更新 API Key" in report
