"""
诊断引擎 - 深度分析问题根因
"""
import os
import re
import json
import time
import socket
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class IssueCategory(Enum):
    API = "api"
    RESOURCE = "resource"
    NETWORK = "network"
    CONFIG = "config"
    STUCK = "stuck"
    UNKNOWN = "unknown"


@dataclass
class DiagnosisResult:
    category: IssueCategory
    root_cause: str
    confidence: float
    evidence: List[str]
    recommendations: List[str]
    related_logs: List[str]


# ── 日志自动发现 ──────────────────────────────────────────────

LOG_SEARCH_PATHS = [
    # Claude Code (Windows)
    Path(os.environ.get("APPDATA", "")) / "Claude" / "logs",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Claude",
    # Claude Code (通用)
    Path.home() / ".claude" / "logs",
    Path.home() / ".claude",
    # OpenClaw
    Path.home() / ".openclaw",
    Path.home() / ".openclaw" / "logs",
    # OpenCode
    Path.home() / ".config" / "opencode" / "logs",
    Path.home() / ".opencode" / "logs",
    # Hermes
    Path.home() / ".hermes" / "sessions",
    # Aider
    Path.home() / ".aider" / "logs",
    Path.home() / ".aider",
    # 临时目录
    Path(os.environ.get("TEMP", "/tmp")),
    Path("/tmp"),
]

LOG_GLOB_PATTERNS = [
    "*.log",
    "*.log.*",
    "*error*",
    "*crash*",
    "*output*",
    "conversation*.json",
    "messages*.json",
    "claude*",
    "openclaw*",
]


class LogDiscoverer:
    """自动发现 OpenClaw / Claude Code 相关日志文件"""

    @staticmethod
    def discover_logs(max_depth: int = 4) -> List[Path]:
        """扫描所有已知路径，返回按修改时间排序的日志文件列表"""
        found: Dict[Path, float] = {}

        for search_path in LOG_SEARCH_PATHS:
            if not search_path or not search_path.exists():
                continue
            try:
                for pattern in LOG_GLOB_PATTERNS:
                    for f in search_path.rglob(pattern):
                        if f.is_file() and f.stat().st_size > 0:
                            found[f] = f.stat().st_mtime
            except PermissionError:
                continue

        # 按最近修改时间排序（最新的在前）
        sorted_paths = sorted(found, key=lambda p: found[p], reverse=True)
        return sorted_paths[:30]  # 最多返回 30 个

    @staticmethod
    def find_active_log(hours: int = 2) -> Optional[Path]:
        """找到最近有写入活动的日志文件"""
        cutoff = time.time() - hours * 3600
        for path in LogDiscoverer.discover_logs():
            try:
                if path.stat().st_mtime >= cutoff:
                    return path
            except OSError:
                continue
        return None

    @staticmethod
    def tail_log(path: Path, n_lines: int = 100) -> List[str]:
        """读取日志文件最后 N 行"""
        if not path or not path.exists():
            return []
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            return [l.rstrip("\n\r") for l in lines[-n_lines:]]
        except Exception as e:
            return [f"<读取日志失败: {e}>"]

    @staticmethod
    def format_log_age(path: Path) -> str:
        """返回日志文件的最后修改时间描述"""
        try:
            age = time.time() - path.stat().st_mtime
            if age < 60:
                return "刚刚"
            elif age < 3600:
                return f"{int(age // 60)} 分钟前"
            elif age < 86400:
                return f"{int(age // 3600)} 小时前"
            else:
                return f"{int(age // 86400)} 天前"
        except OSError:
            return "未知"


# ── 增强诊断引擎 ─────────────────────────────────────────────

class DiagnosticsEngine:
    """深度诊断引擎"""

    # 更全面的错误模式匹配（中英文）
    ERROR_PATTERNS: Dict[str, List[str]] = {
        "context_overflow": [
            r"context\s*(length|overflow|limit|exceed)",
            r"token\s*(limit|exceed|too\s*long|budget)",
            r"maximum\s*context",
            r"too\s*many\s*tokens",
            r"上下文.*(长度|超出|过长|限制)",
            r"token.*(超出|超过|限制)",
        ],
        "api_auth_failed": [
            r"invalid\s*api\s*key",
            r"unauthorized",
            r"authentication\s*(failed|error)",
            r"401|403",
            r"api.?key.*(invalid|wrong|bad)",
            r"认证.*(失败|无效|错误)",
            r"密钥.*(无效|错误)",
        ],
        "rate_limit": [
            r"rate\s*limit",
            r"too\s*many\s*requests",
            r"429",
            r"频率限制",
            r"请求.*过快",
        ],
        "network_timeout": [
            r"timeout",
            r"connection\s*(refused|reset|closed|error)",
            r"network\s*error",
            r"econnrefused|econnreset|etimedout",
            r"dns.*(error|resolution)",
            r"连接.*(超时|拒绝|重置|失败)",
            r"网络.*(错误|不通|异常)",
            r"proxy.*(error|refused)",
            r"代理.*(错误|拒绝)",
        ],
        "memory_issue": [
            r"out\s*of\s*memory",
            r"memory\s*error",
            r"oom",
            r"killed\s*process",
            r"内存.*(不足|耗尽|泄漏)",
            r"signal\s*[9SIGKILL]",
        ],
        "process_crash": [
            r"segmentation\s*fault",
            r"segfault",
            r"core\s*dumped",
            r"abort",
            r"panic",
            r"fatal\s*error",
            r"exit\s*status\s*[1-9]",
            r"进程.*(崩溃|退出|异常)",
        ],
        "process_stuck": [
            r"hang|hung|stuck|freeze|unresponsive",
            r"no\s*response|not\s*responding",
            r"卡死|无响应|假死",
        ],
        "config_error": [
            r"config.*(error|invalid|corrupt|parse)",
            r"cannot\s*(read|parse|load)\s*config",
            r"配置文件.*(错误|无效|损坏|解析)",
        ],
        "model_not_found": [
            r"model\s*not\s*found",
            r"invalid\s*model",
            r"model.*(unavailable|deprecated|not\s*supported)",
            r"模型.*(不存在|不可用|不支持)",
        ],
        "quota_exceeded": [
            r"quota\s*exceeded",
            r"billing\s*limit",
            r"insufficient\s*quota",
            r"配额.*(超出|不足|耗尽)",
            r"余额.*(不足|耗尽)",
        ],
        "disk_full": [
            r"disk.*(full|space|quota)",
            r"no\s*space\s*left",
            r"磁盘.*(满|不足|空间)",
            r"ENOSPC",
        ],
        "signal_killed": [
            r"signal\s*[0-9]",
            r"killed|SIGTERM|SIGKILL|SIGINT",
            r"exit\s*code\s*[-][0-9]",
        ],
    }

    def __init__(self):
        self.log_discoverer = LogDiscoverer()

    def diagnose(self, symptoms: Dict) -> DiagnosisResult:
        """基于症状进行诊断"""
        for method in [
            self._diagnose_api,
            self._diagnose_resource,
            self._diagnose_network,
            self._diagnose_stuck,
            self._diagnose_config,
        ]:
            result = method(symptoms)
            if result.confidence > 0.7:
                return result
        return self._combined_diagnosis(symptoms)

    def diagnose_from_logs(self, log_lines: List[str]) -> Optional[DiagnosisResult]:
        """从日志行内容中诊断问题"""
        if not log_lines:
            return None

        combined_text = "\n".join(log_lines)
        evidence: Dict[str, List[str]] = {}
        latest_line = log_lines[-1] if log_lines else ""

        for category, patterns in self.ERROR_PATTERNS.items():
            matches = []
            for p in patterns:
                try:
                    found = re.findall(p, combined_text, re.IGNORECASE)
                    if found:
                        # 找到匹配的上下文行
                        for line in log_lines:
                            if re.search(p, line, re.IGNORECASE):
                                matches.append(line.strip()[:150])
                                if len(matches) >= 3:
                                    break
                except re.error:
                    continue
            if matches:
                evidence[category] = matches

        if not evidence:
            return None

        # 按优先级排序证据类别
        priority = [
            "process_crash", "signal_killed", "memory_issue", "disk_full",
            "context_overflow", "api_auth_failed", "rate_limit",
            "network_timeout", "process_stuck", "model_not_found",
            "quota_exceeded", "config_error",
        ]

        for cat in priority:
            if cat in evidence:
                mapping = {
                    "process_crash": ("进程崩溃", IssueCategory.RESOURCE,
                                      "进程异常退出，需要重启"),
                    "signal_killed": ("进程被系统终止", IssueCategory.RESOURCE,
                                      "可能是 OOM 或手动终止"),
                    "memory_issue": ("内存溢出", IssueCategory.RESOURCE,
                                     "内存不足导致进程被杀死"),
                    "disk_full": ("磁盘空间不足", IssueCategory.RESOURCE,
                                  "磁盘已满，无法写入数据"),
                    "context_overflow": ("上下文过长", IssueCategory.API,
                                         "Token 数超出模型限制"),
                    "api_auth_failed": ("API 认证失败", IssueCategory.API,
                                        "API Key 无效或已过期"),
                    "rate_limit": ("触发频率限制", IssueCategory.API,
                                   "请求过于频繁被限流"),
                    "network_timeout": ("网络连接异常", IssueCategory.NETWORK,
                                        "无法连接到 API 服务器"),
                    "process_stuck": ("进程卡死", IssueCategory.STUCK,
                                      "进程无响应，需要重启"),
                    "model_not_found": ("模型不可用", IssueCategory.API,
                                        "模型名错误或已下线"),
                    "quota_exceeded": ("API 配额耗尽", IssueCategory.API,
                                       "账户余额或配额不足"),
                    "config_error": ("配置错误", IssueCategory.CONFIG,
                                     "配置文件损坏或格式错误"),
                }
                label, cat_type, desc = mapping.get(cat, (cat, IssueCategory.UNKNOWN, cat))

                recs = self._recommendations_for(cat)
                return DiagnosisResult(
                    category=cat_type,
                    root_cause=f"{label} — {desc}",
                    confidence=0.85 if len(evidence[cat]) >= 2 else 0.7,
                    evidence=evidence[cat][:5],
                    recommendations=recs,
                    related_logs=evidence[cat][:5],
                )

        # 如果有证据但没匹配到优先级列表
        first_cat = list(evidence.keys())[0]
        return DiagnosisResult(
            category=IssueCategory.UNKNOWN,
            root_cause=f"检测到异常模式: {first_cat}",
            confidence=0.5,
            evidence=evidence[first_cat][:3],
            recommendations=self._recommendations_for(first_cat),
            related_logs=evidence[first_cat][:3],
        )

    def _recommendations_for(self, category: str) -> List[str]:
        """根据问题类别返回建议"""
        recs = {
            "context_overflow": [
                "使用 'openscaw fix context' 压缩上下文",
                "开启新的对话会话",
                "调整 max_context_tokens 配置",
            ],
            "api_auth_failed": [
                "检查 API Key 是否过期",
                "使用 'openscaw fix api' 切换到备用 Key",
                "在环境变量中更新 API_KEY",
            ],
            "rate_limit": [
                "等待 1-2 分钟后重试",
                "切换到其他 API 提供商",
                "降低请求频率",
            ],
            "network_timeout": [
                "检查网络连接是否正常",
                "尝试切换代理或 VPN",
                "检查 API 端点是否可访问",
                "使用 'openscaw fix network' 重置网络",
            ],
            "memory_issue": [
                "重启 OpenClaw 释放内存",
                "减少同时打开的对话数量",
                "升级系统内存或使用更小的模型",
            ],
            "process_crash": [
                "查看崩溃日志获取详细原因",
                "使用 'openscaw revive' 重启进程",
                "如频繁崩溃，检查系统资源",
            ],
            "process_stuck": [
                "使用 'openscaw revive' 恢复进程",
                "强制终止并重启进程",
                "检查是否有死循环或等待锁",
            ],
            "config_error": [
                "检查配置文件格式",
                "使用 'openscaw config --edit' 修复配置",
                "恢复默认配置",
            ],
            "model_not_found": [
                "更新模型名称",
                "检查 API 提供商的最新模型列表",
                "切换到其他可用模型",
            ],
            "quota_exceeded": [
                "检查 API 账户余额",
                "升级 API 套餐",
                "切换到其他 API 提供商",
            ],
            "disk_full": [
                "清理磁盘空间",
                "删除无需的日志和临时文件",
                "使用 'openscaw doctor' 查看磁盘使用情况",
            ],
            "signal_killed": [
                "检查系统日志了解终止原因",
                "如 OOM 导致，增加内存或降低负载",
                "使用 'openscaw revive' 重启",
            ],
        }
        return recs.get(category, ["收集更多信息后重试"])

    @staticmethod
    def check_connectivity(host: str = "api.moonshot.cn", port: int = 443, timeout: int = 5) -> Dict:
        """检查网络连通性"""
        result = {"host": host, "reachable": False, "latency_ms": 0, "error": None}
        try:
            start = time.time()
            sock = socket.create_connection((host, port), timeout=timeout)
            result["latency_ms"] = round((time.time() - start) * 1000, 1)
            result["reachable"] = True
            sock.close()
        except socket.gaierror as e:
            result["error"] = f"DNS 解析失败: {e}"
        except socket.timeout:
            result["error"] = f"连接超时 ({timeout}s)"
        except OSError as e:
            result["error"] = f"连接失败: {e}"
        return result

    @staticmethod
    def check_all_endpoints() -> Dict[str, Dict]:
        """检查所有常见 API 端点的连通性"""
        endpoints = [
            ("Moonshot AI", "api.moonshot.cn", 443),
            ("DeepSeek", "api.deepseek.com", 443),
            ("MiniMax", "api.minimax.chat", 443),
        ]
        results = {}
        for name, host, port in endpoints:
            results[name] = DiagnosticsEngine.check_connectivity(host, port)
        return results

    def find_recent_errors(self, log_path: Path, minutes: int = 30) -> List[Dict]:
        """查找日志中最近的错误记录（带时间戳）"""
        if not log_path or not log_path.exists():
            return []

        cutoff = datetime.now() - timedelta(minutes=minutes)
        errors = []

        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    ts = self._extract_timestamp(line)
                    if ts and ts < cutoff:
                        continue
                    # 检查是否包含错误关键词
                    if re.search(r"error|exception|traceback|fail|crash|killed|signal",
                                 line, re.IGNORECASE):
                        errors.append({
                            "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S") if ts else "unknown",
                            "line": line.strip()[:200],
                        })
        except Exception as e:
            logger.warning("读取日志出错: %s", e)

        return errors[-20:]  # 最多返回 20 条

    # ── 内部方法 ──────────────────────────────────────────────

    def _diagnose_api(self, symptoms: Dict) -> DiagnosisResult:
        api_status = symptoms.get("api_status", {})
        errors = symptoms.get("errors", [])

        evidence = []
        recommendations = []

        for api_name, status in api_status.items():
            if "invalid" in status.lower() or "key" in status.lower():
                evidence.append(f"{api_name} API 返回认证错误: {status}")
                recommendations = self._recommendations_for("api_auth_failed")

        for error in errors:
            error_lower = error.lower()
            if any(kw in error_lower for kw in ["invalid api key", "api key", "unauthorized",
                                                 "authentication", "认证", "密钥"]):
                evidence.append(f"API 认证错误: {error[:100]}")
                recommendations = self._recommendations_for("api_auth_failed")

        rate_limited = [n for n, s in api_status.items() if "rate" in s.lower()]
        if rate_limited:
            evidence.append(f"触发频率限制: {', '.join(rate_limited)}")
            recommendations = self._recommendations_for("rate_limit")

        for error in errors:
            if any(kw in error.lower() for kw in ["context", "token", "length", "上下文"]):
                evidence.append(f"上下文相关错误: {error[:100]}")
                recommendations = self._recommendations_for("context_overflow")

        confidence = 0.85 if evidence else 0.3
        return DiagnosisResult(
            category=IssueCategory.API,
            root_cause="API 认证或限制问题" if evidence else "未明确",
            confidence=confidence,
            evidence=evidence,
            recommendations=recommendations,
            related_logs=errors[:5],
        )

    def _diagnose_resource(self, symptoms: Dict) -> DiagnosisResult:
        memory_mb = symptoms.get("memory_mb", 0)
        context_tokens = symptoms.get("context_tokens", 0)
        errors = symptoms.get("errors", [])
        disk_usage = symptoms.get("disk_usage", {})

        evidence = []
        recommendations = []

        if memory_mb > 2000:
            evidence.append(f"内存使用过高: {memory_mb:.0f}MB")
            recommendations = self._recommendations_for("memory_issue")

        if context_tokens > 7000:
            evidence.append(f"上下文过长: {context_tokens} tokens")
            recommendations = self._recommendations_for("context_overflow")

        if disk_usage.get("percent", 0) > 90:
            evidence.append(f"磁盘使用率: {disk_usage['percent']}%")
            recommendations = self._recommendations_for("disk_full")

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
            related_logs=errors[:5],
        )

    def _diagnose_network(self, symptoms: Dict) -> DiagnosisResult:
        response_time = symptoms.get("response_time_ms", 0)
        api_status = symptoms.get("api_status", {})
        errors = symptoms.get("errors", [])

        evidence = []
        recommendations = []

        if response_time > 10000:
            evidence.append(f"响应超时: {response_time:.0f}ms")
            recommendations = self._recommendations_for("network_timeout")

        for error in errors:
            if any(kw in error.lower() for kw in ["timeout", "connection", "refused",
                                                   "network", "reset", "proxy"]):
                evidence.append(f"网络错误: {error[:100]}")

        for api_name, status in api_status.items():
            if "timeout" in status.lower():
                evidence.append(f"{api_name} API 连接超时")

        connectivity = symptoms.get("connectivity", {})
        if connectivity and not connectivity.get("reachable", True):
            evidence.append(f"无法连接到 {connectivity.get('host', 'API 服务器')}")

        confidence = min(0.85, len(evidence) * 0.4 + 0.2)
        return DiagnosisResult(
            category=IssueCategory.NETWORK,
            root_cause="网络连接不稳定" if evidence else "未明确",
            confidence=confidence,
            evidence=evidence,
            recommendations=recommendations or self._recommendations_for("network_timeout"),
            related_logs=errors[:5],
        )

    def _diagnose_stuck(self, symptoms: Dict) -> DiagnosisResult:
        """诊断进程卡死/无响应"""
        process = symptoms.get("process")
        response_time = symptoms.get("response_time_ms", 0)
        log_active = symptoms.get("log_active")
        errors = symptoms.get("errors", [])
        cpu_percent = symptoms.get("cpu_percent", -1)

        evidence = []
        recommendations = []

        if process is None:
            evidence.append("进程未运行")
            recommendations = ["启动 OpenClaw 进程"]
        elif process.status == "zombie":
            evidence.append(f"进程 {process.pid} 是僵尸进程")
            recommendations = self._recommendations_for("process_stuck")
        elif response_time > 30000:
            evidence.append(f"响应时间超长 ({response_time:.0f}ms)")
            recommendations = self._recommendations_for("process_stuck")
            if log_active is False:
                evidence.append("日志文件已停止更新 — 进程可能已卡死")
            if cpu_percent is not None and cpu_percent < 1:
                evidence.append(f"CPU 使用率接近 0% ({cpu_percent}%) — 进程可能挂起")

        for error in errors:
            if any(kw in error.lower() for kw in ["hang", "hung", "stuck", "freeze",
                                                   "no response", "卡死", "无响应"]):
                evidence.append(f"卡死相关日志: {error[:100]}")

        if not evidence:
            return DiagnosisResult(
                category=IssueCategory.STUCK,
                root_cause="未明确",
                confidence=0.2,
                evidence=[],
                recommendations=[],
                related_logs=[],
            )

        confidence = min(0.9, len(evidence) * 0.3 + 0.3)
        return DiagnosisResult(
            category=IssueCategory.STUCK,
            root_cause=f"进程疑似卡死 ({len(evidence)} 条迹象)" if len(evidence) > 1 else "进程可能无响应",
            confidence=confidence,
            evidence=evidence,
            recommendations=recommendations or self._recommendations_for("process_stuck"),
            related_logs=errors[:5],
        )

    def _diagnose_config(self, symptoms: Dict) -> DiagnosisResult:
        recent_changes = symptoms.get("recent_changes", [])
        errors = symptoms.get("errors", [])

        evidence = []
        recommendations = []

        if recent_changes:
            evidence.append(f"近期配置变更: {', '.join(recent_changes)}")
            recommendations.append("检查最近的配置变更是否正确")

        for error in errors:
            if any(kw in error.lower() for kw in ["config", "configuration", "setting", "配置"]):
                evidence.append(f"配置错误: {error[:100]}")
                recommendations = self._recommendations_for("config_error")

        confidence = min(0.8, len(evidence) * 0.5 + 0.1)
        return DiagnosisResult(
            category=IssueCategory.CONFIG,
            root_cause="配置错误或不兼容" if evidence else "未明确",
            confidence=confidence,
            evidence=evidence,
            recommendations=recommendations,
            related_logs=errors[:5],
        )

    def _combined_diagnosis(self, symptoms: Dict) -> DiagnosisResult:
        all_evidence = []
        all_recommendations = [
            "收集更多日志信息",
            "尝试重启 OpenClaw",
            "使用 'openscaw report' 生成详细报告",
        ]

        for method in [self._diagnose_api, self._diagnose_resource,
                       self._diagnose_network, self._diagnose_stuck, self._diagnose_config]:
            result = method(symptoms)
            if result.confidence > 0.3:
                all_evidence.extend(result.evidence)
                all_recommendations.extend(result.recommendations)

        return DiagnosisResult(
            category=IssueCategory.UNKNOWN,
            root_cause="需要进一步调查 — 未找到明确模式",
            confidence=0.3,
            evidence=list(set(all_evidence))[:5],
            recommendations=list(set(all_recommendations))[:5],
            related_logs=symptoms.get("errors", [])[:5],
        )

    def analyze_logs(self, log_path: Path, hours: int = 24) -> Dict:
        """增强版日志分析"""
        if not log_path or not log_path.exists():
            return {"error": f"日志文件不存在: {log_path}"}

        cutoff_time = datetime.now() - timedelta(hours=hours)
        errors = []
        warnings = []
        patterns_found = {}

        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    ts = self._extract_timestamp(line)
                    if ts and ts < cutoff_time:
                        continue

                    if "ERROR" in line or "error" in line.lower():
                        errors.append(line.strip()[:200])
                    elif "WARN" in line or "warning" in line.lower():
                        warnings.append(line.strip()[:200])

                    # 匹配已知模式
                    for pattern_name, patterns in self.ERROR_PATTERNS.items():
                        for p in patterns:
                            if re.search(p, line, re.IGNORECASE):
                                patterns_found[pattern_name] = patterns_found.get(pattern_name, 0) + 1
                                break
        except Exception as e:
            return {"error": f"读取日志失败: {e}"}

        return {
            "time_range": f"{hours} hours",
            "total_errors": len(errors),
            "total_warnings": len(warnings),
            "error_samples": errors[-15:],
            "warning_samples": warnings[-15:],
            "pattern_matches": dict(sorted(patterns_found.items(), key=lambda x: -x[1])),
        }

    @staticmethod
    def _extract_timestamp(line: str) -> Optional[datetime]:
        """提取日志行中的时间戳"""
        patterns = [
            r"(\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}:\d{2})",
            r"(\d{2}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2})",
            r"(\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})",
        ]
        for p in patterns:
            m = re.search(p, line)
            if m:
                try:
                    ts_str = m.group(1)
                    if "/" in ts_str:
                        return datetime.strptime(ts_str, "%m/%d/%y %H:%M:%S")
                    elif " " in ts_str and ts_str.count("-") == 2:
                        return datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                    elif "T" in ts_str:
                        return datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%S")
                except ValueError:
                    continue
        return None

    def generate_report(self, diagnosis: DiagnosisResult, symptoms: Dict) -> str:
        lines = [
            "=" * 60,
            "              OpenScaw 诊断报告",
            "=" * 60,
            "",
            f"问题类别: {diagnosis.category.value.upper()}",
            "",
            f"根因分析: {diagnosis.root_cause}",
            f"   置信度: {diagnosis.confidence * 100:.0f}%",
            "",
        ]

        if diagnosis.evidence:
            lines.append("证据:")
            for i, ev in enumerate(diagnosis.evidence, 1):
                lines.append(f"   {i}. {ev}")
            lines.append("")

        if diagnosis.recommendations:
            lines.append("建议:")
            for i, rec in enumerate(diagnosis.recommendations, 1):
                lines.append(f"   {i}. {rec}")
            lines.append("")

        lines.extend([
            "-" * 60,
            "当前状态:",
            f"   上下文长度: {symptoms.get('context_tokens', 'N/A')} tokens",
            f"   内存使用: {symptoms.get('memory_mb', 'N/A')} MB",
            f"   响应时间: {symptoms.get('response_time_ms', 'N/A')} ms",
            "",
            "API 状态:",
        ])

        for api, status in symptoms.get("api_status", {}).items():
            icon = "[OK]" if status == "healthy" else "[FAIL]"
            lines.append(f"   {icon} {api}: {status}")

        lines.append("")
        lines.append("=" * 60)
        return "\n".join(lines)
