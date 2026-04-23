"""
诊断引擎 - 深度分析问题根因
"""
import os
import re
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class IssueCategory(Enum):
    API = "api"
    RESOURCE = "resource"
    NETWORK = "network"
    CONFIG = "config"
    UNKNOWN = "unknown"

@dataclass
class DiagnosisResult:
    category: IssueCategory
    root_cause: str
    confidence: float  # 0-1
    evidence: List[str]
    recommendations: List[str]
    related_logs: List[str]

class DiagnosticsEngine:
    """深度诊断引擎"""
    
    def __init__(self):
        self._patterns = self._load_patterns()
    
    def diagnose(self, symptoms: Dict) -> DiagnosisResult:
        """
        基于症状进行诊断
        
        Args:
            symptoms: 包含以下键的字典
                - errors: 错误消息列表
                - api_status: API状态字典
                - context_tokens: 当前上下文token数
                - memory_mb: 内存使用
                - response_time_ms: 响应时间
                - recent_changes: 最近的配置变更
        """
        # 1. API 相关诊断
        api_result = self._diagnose_api(symptoms)
        if api_result.confidence > 0.7:
            return api_result
        
        # 2. 资源相关诊断
        resource_result = self._diagnose_resource(symptoms)
        if resource_result.confidence > 0.7:
            return resource_result
        
        # 3. 网络相关诊断
        network_result = self._diagnose_network(symptoms)
        if network_result.confidence > 0.6:
            return network_result
        
        # 4. 配置相关诊断
        config_result = self._diagnose_config(symptoms)
        if config_result.confidence > 0.6:
            return config_result
        
        # 综合判断
        return self._combined_diagnosis(symptoms)
    
    def _diagnose_api(self, symptoms: Dict) -> DiagnosisResult:
        """诊断 API 相关问题"""
        api_status = symptoms.get("api_status", {})
        errors = symptoms.get("errors", [])
        
        evidence = []
        recommendations = []
        
        # 检查 API Key 失效 - 从 api_status 检查
        for api_name, status in api_status.items():
            if "invalid" in status.lower() or "key" in status.lower():
                evidence.append(f"{api_name} API 返回认证错误: {status}")
                recommendations.extend([
                    f"检查 {api_name} 的 API Key 是否过期",
                    f"在环境变量中更新 {api_name.upper()}_API_KEY",
                    f"或使用 'openscaw fix api_key' 切换到备用 Key"
                ])
        
        # 检查错误消息中的 API Key 问题
        for error in errors:
            error_lower = error.lower()
            if any(kw in error_lower for kw in ["invalid api key", "api key", "unauthorized", "authentication", "认证", "密钥"]):
                evidence.append(f"API 认证错误: {error[:100]}")
                recommendations.extend([
                    "检查 API Key 是否过期",
                    "使用 'openscaw fix api_key' 切换到备用 Key",
                    "在环境变量中更新 API_KEY"
                ])
        
        # 检查频率限制
        rate_limited = [name for name, status in api_status.items() 
                       if "rate" in status.lower()]
        if rate_limited:
            evidence.append(f"触发频率限制: {', '.join(rate_limited)}")
            recommendations.extend([
                "等待一段时间后重试",
                "切换到其他 API",
                "降低请求频率"
            ])
        
        # 检查上下文长度
        for error in errors:
            if any(kw in error.lower() for kw in ["context", "token", "length", "上下文"]):
                evidence.append(f"上下文相关错误: {error[:100]}")
                recommendations.extend([
                    "使用 'openscaw fix context' 压缩上下文",
                    "开启新的对话会话",
                    "调整 max_context_tokens 配置"
                ])
        
        # 只要有 API 相关证据，就给高置信度
        confidence = 0.85 if evidence else 0.3
        
        return DiagnosisResult(
            category=IssueCategory.API,
            root_cause="API 认证或限制问题" if evidence else "未明确",
            confidence=confidence,
            evidence=evidence,
            recommendations=recommendations,
            related_logs=errors[:5]
        )
    
    def _diagnose_resource(self, symptoms: Dict) -> DiagnosisResult:
        """诊断资源相关问题"""
        memory_mb = symptoms.get("memory_mb", 0)
        context_tokens = symptoms.get("context_tokens", 0)
        errors = symptoms.get("errors", [])
        
        evidence = []
        recommendations = []
        
        # 内存问题
        if memory_mb > 2000:
            evidence.append(f"内存使用过高: {memory_mb:.0f}MB")
            recommendations.extend([
                "重启 OpenClaw 进程",
                "检查是否有内存泄漏",
                "考虑使用更小的模型"
            ])
        
        # 上下文过长
        if context_tokens > 7000:
            evidence.append(f"上下文过长: {context_tokens} tokens")
            recommendations.extend([
                "清理对话历史",
                "开启新会话",
                "使用上下文压缩功能"
            ])
        
        # 检查内存相关错误
        for error in errors:
            if any(kw in error.lower() for kw in ["memory", "oom", "out of memory", "内存"]):
                evidence.append(f"内存错误: {error[:100]}")
        
        confidence = min(0.9, len(evidence) * 0.35 + 0.2)
        
        return DiagnosisResult(
            category=IssueCategory.RESOURCE,
            root_cause="资源不足或泄漏" if evidence else "未明确",
            confidence=confidence,
            evidence=evidence,
            recommendations=recommendations,
            related_logs=errors[:5]
        )
    
    def _diagnose_network(self, symptoms: Dict) -> DiagnosisResult:
        """诊断网络相关问题"""
        response_time = symptoms.get("response_time_ms", 0)
        api_status = symptoms.get("api_status", {})
        errors = symptoms.get("errors", [])
        
        evidence = []
        recommendations = []
        
        # 响应时间过长
        if response_time > 10000:
            evidence.append(f"响应超时: {response_time:.0f}ms")
            recommendations.extend([
                "检查网络连接",
                "切换 API 节点",
                "使用代理或 VPN"
            ])
        
        # 连接错误
        for error in errors:
            if any(kw in error.lower() for kw in ["timeout", "connection", "refused", "network"]):
                evidence.append(f"连接错误: {error[:100]}")
        
        # API 超时
        for api_name, status in api_status.items():
            if "timeout" in status.lower():
                evidence.append(f"{api_name} API 连接超时")
        
        confidence = min(0.85, len(evidence) * 0.4 + 0.2)
        
        return DiagnosisResult(
            category=IssueCategory.NETWORK,
            root_cause="网络连接不稳定" if evidence else "未明确",
            confidence=confidence,
            evidence=evidence,
            recommendations=recommendations,
            related_logs=errors[:5]
        )
    
    def _diagnose_config(self, symptoms: Dict) -> DiagnosisResult:
        """诊断配置相关问题"""
        recent_changes = symptoms.get("recent_changes", [])
        errors = symptoms.get("errors", [])
        
        evidence = []
        recommendations = []
        
        # 最近的配置变更
        if recent_changes:
            evidence.append(f"近期配置变更: {', '.join(recent_changes)}")
            recommendations.append("检查最近的配置变更是否正确")
        
        # 配置相关错误
        for error in errors:
            if any(kw in error.lower() for kw in ["config", "configuration", "setting", "配置"]):
                evidence.append(f"配置错误: {error[:100]}")
                recommendations.extend([
                    "检查配置文件格式",
                    "恢复默认配置进行测试",
                    "使用 'openscaw doctor' 进行配置诊断"
                ])
        
        confidence = min(0.8, len(evidence) * 0.5 + 0.1)
        
        return DiagnosisResult(
            category=IssueCategory.CONFIG,
            root_cause="配置错误或不兼容" if evidence else "未明确",
            confidence=confidence,
            evidence=evidence,
            recommendations=recommendations,
            related_logs=errors[:5]
        )
    
    def _combined_diagnosis(self, symptoms: Dict) -> DiagnosisResult:
        """综合诊断 - 当没有明确类别时"""
        all_evidence = []
        all_recommendations = [
            "收集更多日志信息",
            "尝试重启 OpenClaw",
            "使用 'openscaw report' 生成详细报告"
        ]
        
        # 合并所有诊断的线索
        for method in [self._diagnose_api, self._diagnose_resource, 
                      self._diagnose_network, self._diagnose_config]:
            result = method(symptoms)
            if result.confidence > 0.3:
                all_evidence.extend(result.evidence)
                all_recommendations.extend(result.recommendations)
        
        return DiagnosisResult(
            category=IssueCategory.UNKNOWN,
            root_cause="需要进一步调查",
            confidence=0.3,
            evidence=list(set(all_evidence))[:5],
            recommendations=list(set(all_recommendations))[:5],
            related_logs=symptoms.get("errors", [])[:5]
        )
    
    def analyze_logs(self, log_path: Path, hours: int = 24) -> Dict:
        """
        分析日志文件
        
        Args:
            log_path: 日志文件路径
            hours: 分析最近多少小时的日志
        """
        if not log_path.exists():
            return {"error": f"日志文件不存在: {log_path}"}
        
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        errors = []
        warnings = []
        patterns_found = {}
        
        with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                # 尝试解析时间戳
                try:
                    # 常见日志时间格式
                    time_match = re.search(r'\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}:\d{2}', line)
                    if time_match:
                        log_time = datetime.strptime(time_match.group(), '%Y-%m-%d %H:%M:%S')
                        if log_time < cutoff_time:
                            continue
                except:
                    pass
                
                # 分类日志级别
                if 'ERROR' in line or 'error' in line.lower():
                    errors.append(line.strip())
                elif 'WARN' in line or 'warning' in line.lower():
                    warnings.append(line.strip())
                
                # 匹配已知模式
                for pattern_name, pattern in self._patterns.items():
                    if re.search(pattern, line, re.IGNORECASE):
                        patterns_found[pattern_name] = patterns_found.get(pattern_name, 0) + 1
        
        return {
            "time_range": f"{hours} hours",
            "total_errors": len(errors),
            "total_warnings": len(warnings),
            "error_samples": errors[-10:],
            "warning_samples": warnings[-10:],
            "pattern_matches": patterns_found
        }
    
    def _load_patterns(self) -> Dict[str, str]:
        """加载诊断模式"""
        return {
            "context_overflow": r"context.*length|token.*limit|maximum.*context",
            "api_auth_failed": r"invalid.*api.*key|unauthorized|authentication.*failed",
            "rate_limit": r"rate.*limit|too.*many.*requests|429",
            "network_timeout": r"timeout|connection.*refused|network.*error",
            "memory_issue": r"out.*of.*memory|memory.*error|oom",
            "config_error": r"config.*error|invalid.*setting|configuration",
            "model_not_found": r"model.*not.*found|invalid.*model",
            "quota_exceeded": r"quota.*exceeded|billing.*limit"
        }
    
    def generate_report(self, diagnosis: DiagnosisResult, 
                       symptoms: Dict) -> str:
        """生成诊断报告"""
        lines = [
            "=" * 60,
            "              OpenScaw 诊断报告",
            "=" * 60,
            f"",
            f"📋 问题类别: {diagnosis.category.value.upper()}",
            f"",
            f"🔍 根因分析: {diagnosis.root_cause}",
            f"   置信度: {diagnosis.confidence * 100:.0f}%",
            f"",
        ]
        
        if diagnosis.evidence:
            lines.append("💡 证据:")
            for i, ev in enumerate(diagnosis.evidence, 1):
                lines.append(f"   {i}. {ev}")
            lines.append("")
        
        if diagnosis.recommendations:
            lines.append("🚀 建议:")
            for i, rec in enumerate(diagnosis.recommendations, 1):
                lines.append(f"   {i}. {rec}")
            lines.append("")
        
        lines.extend([
            "-" * 60,
            "📈 当前状态:",
            f"   上下文长度: {symptoms.get('context_tokens', 'N/A')} tokens",
            f"   内存使用: {symptoms.get('memory_mb', 'N/A')} MB",
            f"   响应时间: {symptoms.get('response_time_ms', 'N/A')} ms",
            "",
            "📝 API 状态:",
        ])
        
        for api, status in symptoms.get('api_status', {}).items():
            icon = "✅" if status == "healthy" else "❌"
            lines.append(f"   {icon} {api}: {status}")
        
        lines.append("")
        lines.append("=" * 60)
        
        return "\n".join(lines)
