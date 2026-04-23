"""监控核心 - 检测 OpenClaw 运行状态"""
import os
import re
import time
import psutil
import asyncio
import logging
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Callable
from enum import Enum

from .config import ConfigManager, MonitorConfig
from .api_client import APIClientManager, APIStatus

logger = logging.getLogger(__name__)

class HealthLevel(Enum):
    HEALTHY = "healthy"      # 健康
    WARNING = "warning"      # 警告
    CRITICAL = "critical"    # 严重
    UNKNOWN = "unknown"      # 未知

@dataclass
class ProcessInfo:
    pid: int
    name: str
    memory_mb: float
    cpu_percent: float
    status: str
    created: datetime
    cmdline: str = ""

@dataclass
class HealthReport:
    timestamp: datetime
    level: HealthLevel
    process: Optional[ProcessInfo]
    api_status: Dict[str, str]
    context_tokens: int
    response_time_ms: float
    errors: List[str]
    suggestions: List[str]
    details: Dict = field(default_factory=dict)

class OpenClawMonitor:
    """OpenClaw 健康监控器"""
    
    # 常见的 OpenClaw 类项目进程名
    TARGET_PATTERNS = [
        r"openclaw",
        r"claude-code",
        r"opencode",
        r"hermes.*agent",
        r"aider",
        r"codex",
    ]
    
    def __init__(self, config: ConfigManager = None):
        self.config = config or ConfigManager()
        self.monitor_cfg = self.config.get_monitor_config()
        self.api_manager = APIClientManager()
        
        self._callbacks: List[Callable] = []
        self._running = False
        self._last_context_tokens = 0
        self._error_history: List[str] = []
        self._response_times: List[float] = []
        
    def register_callback(self, callback: Callable):
        """注册状态变化回调"""
        self._callbacks.append(callback)
    
    async def start(self):
        """启动监控循环"""
        self._running = True
        logger.info("🚀 监控已启动")
        
        while self._running:
            try:
                report = await self.check_health()
                
                # 触发回调
                for callback in self._callbacks:
                    try:
                        callback(report)
                    except Exception as e:
                        logger.error(f"回调执行失败: {e}")
                
                await asyncio.sleep(self.monitor_cfg.check_interval)
                
            except Exception as e:
                logger.error(f"监控循环异常: {e}")
                await asyncio.sleep(5)
    
    def stop(self):
        """停止监控"""
        self._running = False
        logger.info("😴 监控已停止")
    
    async def check_health(self) -> HealthReport:
        """执行一次完整健康检查"""
        timestamp = datetime.now()
        
        # 1. 检查进程
        process = self._check_process()
        
        # 2. 检查 API 状态
        api_status = await self._check_apis()
        
        # 3. 检查上下文长度
        context_tokens = self._check_context_length()
        
        # 4. 检查响应时间
        response_time = await self._check_response_time()
        
        # 5. 扫描错误日志
        errors = self._scan_error_logs()
        
        # 6. 综合评估
        level = self._evaluate_health(process, api_status, context_tokens, 
                                       response_time, errors)
        
        # 7. 生成建议
        suggestions = self._generate_suggestions(
            level, process, api_status, context_tokens, response_time, errors
        )
        
        report = HealthReport(
            timestamp=timestamp,
            level=level,
            process=process,
            api_status=api_status,
            context_tokens=context_tokens,
            response_time_ms=response_time,
            errors=errors,
            suggestions=suggestions,
            details={
                "check_interval": self.monitor_cfg.check_interval,
                "memory_threshold": self.monitor_cfg.memory_threshold_mb,
                "context_threshold": self.monitor_cfg.max_context_tokens
            }
        )
        
        # 记录历史
        if response_time > 0:
            self._response_times.append(response_time)
            if len(self._response_times) > 100:
                self._response_times = self._response_times[-100:]
        
        return report
    
    def _check_process(self) -> Optional[ProcessInfo]:
        """检查目标进程"""
        for proc in psutil.process_iter(['pid', 'name', 'memory_info', 
                                          'cpu_percent', 'status', 
                                          'create_time', 'cmdline']):
            try:
                proc_name = proc.info['name'] or ""
                cmdline = ' '.join(proc.info['cmdline'] or [])
                
                # 匹配目标模式
                for pattern in self.TARGET_PATTERNS:
                    if re.search(pattern, proc_name, re.IGNORECASE) or \
                       re.search(pattern, cmdline, re.IGNORECASE):
                        return ProcessInfo(
                            pid=proc.info['pid'],
                            name=proc_name,
                            memory_mb=proc.info['memory_info'].rss / 1024 / 1024,
                            cpu_percent=proc.info['cpu_percent'] or 0,
                            status=proc.info['status'],
                            created=datetime.fromtimestamp(proc.info['create_time']),
                            cmdline=cmdline[:200]  # 限制长度
                        )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        return None
    
    async def _check_apis(self) -> Dict[str, str]:
        """检查所有 API 状态"""
        results = {}
        for name, client in self.api_manager.clients.items():
            try:
                resp = client.test_connection(timeout=5)
                results[name] = resp.status.value
            except Exception as e:
                results[name] = f"error: {str(e)[:50]}"
        return results
    
    def _check_context_length(self) -> int:
        """检查上下文长度（从常见的位置）"""
        # 常见的对话历史文件路径
        possible_paths = [
            Path.home() / ".openclaw" / "conversation.json",
            Path.home() / ".claude" / "conversations.json",
            Path.home() / ".config" / "opencode" / "history.json",
            Path.home() / ".hermes" / "sessions" / "context.json",
        ]
        
        for path in possible_paths:
            if path.exists():
                try:
                    import json
                    data = json.loads(path.read_text(encoding='utf-8'))
                    # 估算 token 数（简单估算：每4个字符约1个 token）
                    text = json.dumps(data)
                    self._last_context_tokens = len(text) // 4
                    return self._last_context_tokens
                except Exception:
                    continue
        
        # 如果没有找到文件，返回上次的值
        return self._last_context_tokens
    
    async def _check_response_time(self) -> float:
        """测试 API 响应时间"""
        client = self.api_manager.get_client()
        if not client:
            return -1
        
        result = client.test_connection(timeout=self.monitor_cfg.response_timeout)
        return result.response_time_ms
    
    def _scan_error_logs(self) -> List[str]:
        """扫描错误日志"""
        errors = []
        
        # 常见的日志路径
        log_paths = [
            Path.home() / ".openclaw" / "logs" / "error.log",
            Path.home() / ".openclaw" / "openclaw.log",
            Path.home() / ".claude" / "logs" / "claude.log",
            Path.home() / ".config" / "opencode" / "logs" / "app.log",
        ]
        
        # 错误关键词模式
        error_patterns = [
            r"context length exceeded",
            r"rate limit",
            r"invalid.*api.*key",
            r"authentication failed",
            r"connection.*(timeout|refused)",
            r"out of memory",
            r"maximum context length",
            r"token.*limit",
            r"上下文长度超出",
            r"API密钥无效",
        ]
        
        for log_path in log_paths:
            if log_path.exists():
                try:
                    content = log_path.read_text(encoding='utf-8', errors='ignore')
                    lines = content.split('\n')
                    # 只看最近5分钟的日志（假设日志有时间戳）
                    recent_lines = lines[-100:] if len(lines) > 100 else lines
                    
                    for line in recent_lines:
                        for pattern in error_patterns:
                            if re.search(pattern, line, re.IGNORECASE):
                                errors.append(line.strip()[:200])
                                if len(errors) >= 5:  # 最多5条
                                    return errors
                except Exception:
                    continue
        
        return errors
    
    def _evaluate_health(self, process, api_status, context_tokens, 
                         response_time, errors) -> HealthLevel:
        """评估整体健康状态"""
        # Critical 条件
        if process is None:
            return HealthLevel.CRITICAL
        
        if any("invalid" in status or "expired" in status 
               for status in api_status.values()):
            return HealthLevel.CRITICAL
        
        if process.memory_mb > self.monitor_cfg.memory_threshold_mb * 2:
            return HealthLevel.CRITICAL
        
        # Warning 条件
        if context_tokens > self.monitor_cfg.max_context_tokens * 0.8:
            return HealthLevel.WARNING
        
        if response_time > self.monitor_cfg.response_timeout * 1000:
            return HealthLevel.WARNING
        
        if process.memory_mb > self.monitor_cfg.memory_threshold_mb:
            return HealthLevel.WARNING
        
        if process.cpu_percent > self.monitor_cfg.cpu_threshold_percent:
            return HealthLevel.WARNING
        
        if errors:
            return HealthLevel.WARNING
        
        return HealthLevel.HEALTHY
    
    def _generate_suggestions(self, level, process, api_status, 
                              context_tokens, response_time, errors) -> List[str]:
        """生成修复建议"""
        suggestions = []
        
        if level == HealthLevel.HEALTHY:
            suggestions.append("✅ 所有指标正常")
            return suggestions
        
        if process is None:
            suggestions.append("🚨 进程未运行，建议启动 OpenClaw")
            return suggestions
        
        # 上下文过长
        if context_tokens > self.monitor_cfg.max_context_tokens * 0.8:
            suggestions.append(f"⚠️ 上下文接近限制 ({context_tokens}/{self.monitor_cfg.max_context_tokens} tokens)")
            suggestions.append("   建议: 使用 'openscaw fix context' 压缩上下文")
        
        # API 问题
        for api_name, status in api_status.items():
            if "invalid" in status:
                suggestions.append(f"🔐 {api_name} API Key 无效，建议更新或切换")
            elif "rate" in status:
                suggestions.append(f"⏰ {api_name} 触发频率限制，建议等待或切换 API")
        
        # 响应慢
        if response_time > 10000:
            suggestions.append(f"🐢 响应较慢 ({response_time:.0f}ms)，可能网络不稳定")
        
        # 资源使用高
        if process.memory_mb > self.monitor_cfg.memory_threshold_mb:
            suggestions.append(f"📊 内存使用较高 ({process.memory_mb:.0f}MB)")
        
        # 错误日志
        if errors:
            suggestions.append(f"🐛 发现 {len(errors)} 个错误，建议查看日志")
        
        return suggestions