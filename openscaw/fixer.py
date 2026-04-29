"""
自动修复模块 - 处理常见问题
"""
import os
import re
import signal
import subprocess
import asyncio
import logging
import psutil
from typing import Dict, List, Optional, Callable
from enum import Enum
from dataclasses import dataclass

from .monitor import OpenClawMonitor, HealthLevel, HealthReport
from .api_client import APIClientManager
from .config import ConfigManager
from .diagnostics import DiagnosticsEngine, LogDiscoverer

logger = logging.getLogger(__name__)

class FixResult(Enum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    MANUAL_REQUIRED = "manual_required"

@dataclass
class FixAction:
    name: str
    description: str
    handler: Callable
    auto_enabled: bool = True

class AutoFixer:
    """自动问题修复器"""
    
    def __init__(self, monitor: OpenClawMonitor = None, 
                 config: ConfigManager = None):
        self.monitor = monitor
        self.config = config or ConfigManager()
        self.api_manager = APIClientManager()
        self.strategies = self.config.get_fix_strategies()
        
        self._fix_history: List[Dict] = []
        self._consecutive_failures: Dict[str, int] = {}
        
        self.diagnostics = DiagnosticsEngine()
        self.log_discoverer = LogDiscoverer()

        # 注册修复动作
        self.actions = {
            "context_overflow": FixAction(
                "context_overflow",
                "压缩上下文长度",
                self._fix_context_overflow
            ),
            "api_key_invalid": FixAction(
                "api_key_invalid",
                "切换API Key",
                self._fix_api_key
            ),
            "process_stuck": FixAction(
                "process_stuck",
                "重启进程",
                self._fix_process_stuck
            ),
            "no_response": FixAction(
                "no_response",
                "唤醒进程",
                self._fix_no_response
            ),
            "memory_high": FixAction(
                "memory_high",
                "内存优化",
                self._fix_memory_high
            ),
            "zombie_process": FixAction(
                "zombie_process",
                "强制清理僵尸进程",
                self._fix_zombie_process
            ),
            "network_issue": FixAction(
                "network_issue",
                "重置网络连接",
                self._fix_network_issue
            ),
            "log_overflow": FixAction(
                "log_overflow",
                "清理日志文件",
                self._fix_log_overflow
            ),
        }
    
    async def auto_fix(self, report: HealthReport) -> Dict[str, FixResult]:
        """根据健康报告自动修复问题（增强版：先查日志，再对症下药）"""
        results = {}

        if report.level == HealthLevel.HEALTHY:
            return {"status": FixResult.SKIPPED, "reason": "系统健康，无需修复"}

        fixes_to_try = []

        # ── 0. 检测僵尸进程（最高优先级） ──
        if report.process and report.process.status == "zombie":
            fixes_to_try.append("zombie_process")

        # ── 1. 进程不存在 ──
        elif report.process is None:
            fixes_to_try.append("process_stuck")

        # ── 2. 查日志，根据日志证据选择修复 ──
        else:
            active_log = self.log_discoverer.find_active_log(hours=1)
            if active_log:
                log_lines = self.log_discoverer.tail_log(active_log, n_lines=200)
                diag = self.diagnostics.diagnose_from_logs(log_lines)
                if diag and diag.confidence > 0.6:
                    log_based = self._map_diagnosis_to_fixes(diag.category.value, report)
                    fixes_to_try.extend(log_based)

            # ── 3. 备选方案：基于报告指标 ──
            if not fixes_to_try:
                # API Key 失效
                if any("invalid" in status for status in report.api_status.values()):
                    fixes_to_try.append("api_key_invalid")

                # 上下文过长
                if report.context_tokens > self.config.get_monitor_config().max_context_tokens * 0.8:
                    fixes_to_try.append("context_overflow")

                # 无响应（响应时间异常）
                if report.response_time_ms < 0 or report.response_time_ms > 10000:
                    fixes_to_try.append("no_response")

                # 内存过高
                if report.process and report.process.memory_mb > self.config.get_monitor_config().memory_threshold_mb:
                    fixes_to_try.append("memory_high")

                # 网络问题
                if report.response_time_ms > 15000:
                    fixes_to_try.append("network_issue")

        # 执行修复
        for fix_name in fixes_to_try:
            if fix_name not in self.actions:
                continue
            result = await self.fix(fix_name)
            results[fix_name] = result
            if result == FixResult.SUCCESS:
                break

        return results

    def _map_diagnosis_to_fixes(self, category: str, report) -> List[str]:
        """将诊断类别映射到修复策略"""
        mapping = {
            "api": ["api_key_invalid", "network_issue"],
            "resource": ["memory_high", "context_overflow", "log_overflow"],
            "network": ["network_issue", "no_response"],
            "stuck": ["no_response", "process_stuck"],
            "config": [],
        }
        return mapping.get(category, [])
    
    async def fix(self, issue: str) -> FixResult:
        """执行指定修复"""
        action = self.actions.get(issue)
        if not action:
            logger.warning(f"未知的修复类型: {issue}")
            return FixResult.FAILED
        
        # 检查是否允许自动修复
        strategy = self.strategies.get(issue, {})
        if not strategy.get("enabled", True):
            logger.info(f"修复 {issue} 已禁用")
            return FixResult.SKIPPED
        
        # 检查连续失败次数
        failures = self._consecutive_failures.get(issue, 0)
        max_retries = strategy.get("max_retries", 3)
        if failures >= max_retries:
            logger.warning(f"修复 {issue} 已连续失败 {failures} 次，需要人工介入")
            return FixResult.MANUAL_REQUIRED
        
        logger.info(f"🛠️  执行修复: {action.description}")
        
        try:
            result = await action.handler()
            
            if result:
                self._consecutive_failures[issue] = 0
                self._fix_history.append({
                    "issue": issue,
                    "result": "success",
                    "timestamp": asyncio.get_event_loop().time()
                })
                logger.info(f"✅ 修复成功: {issue}")
                return FixResult.SUCCESS
            else:
                self._consecutive_failures[issue] = failures + 1
                logger.error(f"❌ 修复失败: {issue}")
                return FixResult.FAILED
                
        except Exception as e:
            self._consecutive_failures[issue] = failures + 1
            logger.exception(f"修复 {issue} 时发生异常: {e}")
            return FixResult.FAILED
    
    async def _fix_context_overflow(self) -> bool:
        """修复上下文过长 - 发送压缩信号或清理历史"""
        methods = [
            self._send_signal_to_compress,
            self._clean_conversation_history,
            self._rotate_log_files,
        ]
        
        for method in methods:
            try:
                if await method():
                    return True
            except Exception as e:
                logger.error(f"压缩上下文方法失败: {e}")
                continue
        
        return False
    
    async def _send_signal_to_compress(self) -> bool:
        """发送信号给 OpenClaw 压缩上下文"""
        process = self._find_openclaw_process()
        if not process:
            return False
        
        try:
            # 尝试发送 USR1 信号（需要 OpenClaw 支持）
            os.kill(process.pid, signal.SIGUSR1)
            logger.info(f"已发送 SIGUSR1 到进程 {process.pid}")
            return True
        except (ProcessLookupError, PermissionError, OSError):
            return False
    
    async def _clean_conversation_history(self) -> bool:
        """清理对话历史文件"""
        from pathlib import Path
        
        history_paths = [
            Path.home() / ".openclaw" / "conversation.json",
            Path.home() / ".openclaw" / "history.json",
            Path.home() / ".claude" / "conversations.json",
        ]
        
        for path in history_paths:
            if path.exists():
                try:
                    # 备份并清空
                    backup = path.with_suffix('.json.backup')
                    import shutil
                    shutil.copy(path, backup)
                    
                    # 保留最后10条消息
                    import json
                    data = json.loads(path.read_text())
                    if isinstance(data, list) and len(data) > 10:
                        data = data[-10:]
                        path.write_text(json.dumps(data, ensure_ascii=False))
                        logger.info(f"已清理历史文件: {path}")
                        return True
                except Exception as e:
                    logger.error(f"清理历史失败: {e}")
        
        return False
    
    async def _rotate_log_files(self) -> bool:
        """轮转日志文件"""
        from pathlib import Path
        
        log_paths = [
            Path.home() / ".openclaw" / "logs" / "openclaw.log",
            Path.home() / ".openclaw" / "openclaw.log",
        ]
        
        for path in log_paths:
            if path.exists() and path.stat().st_size > 10 * 1024 * 1024:  # > 10MB
                try:
                    backup = path.with_suffix('.log.old')
                    path.rename(backup)
                    logger.info(f"已轮转日志: {path}")
                    return True
                except Exception as e:
                    logger.error(f"轮转日志失败: {e}")
        
        return False
    
    async def _fix_api_key(self) -> bool:
        """修复 API Key 问题 - 切换到下一个可用 Key"""
        return self.api_manager.switch_to_next()
    
    async def _fix_process_stuck(self) -> bool:
        """修复进程卡死 - 优雅重启"""
        process = self._find_openclaw_process()
        
        if process:
            # 尝试优雅终止
            try:
                process.terminate()
                await asyncio.sleep(2)
                
                if process.is_running():
                    process.kill()
                    await asyncio.sleep(1)
                
                logger.info(f"已终止进程 {process.pid}")
            except Exception as e:
                logger.error(f"终止进程失败: {e}")
        
        # 尝试重新启动
        return await self._restart_openclaw()
    
    async def _fix_zombie_process(self) -> bool:
        """强制清理僵尸进程"""
        process = self._find_openclaw_process()
        if not process:
            return True  # 没有进程也算清理成功

        pid = process.pid
        logger.warning("清理僵尸进程 PID=%d", pid)

        try:
            # 先 SIGTERM
            os.kill(pid, signal.SIGTERM)
            await asyncio.sleep(2)
        except ProcessLookupError:
            pass
        except Exception as e:
            logger.error("SIGTERM 失败: %s", e)

        try:
            # 如果还在就 SIGKILL
            if psutil.pid_exists(pid):
                os.kill(pid, signal.SIGKILL)
                await asyncio.sleep(1)
                logger.info("已 SIGKILL 僵尸进程 %d", pid)
        except Exception as e:
            logger.error("SIGKILL 失败: %s", e)

        # 验证是否已清除
        return not psutil.pid_exists(pid)

    async def _fix_network_issue(self) -> bool:
        """重置网络连接 — 检查各 API 端点连通性并尝试恢复"""
        endpoints = [
            ("Moonshot AI", "api.moonshot.cn", 443),
            ("DeepSeek", "api.deepseek.com", 443),
            ("MiniMax", "api.minimax.chat", 443),
        ]

        all_ok = True
        for name, host, port in endpoints:
            try:
                import socket
                sock = socket.create_connection((host, port), timeout=5)
                sock.close()
                logger.info("网络连通: %s (%s)", name, host)
            except Exception as e:
                all_ok = False
                logger.warning("网络不通: %s (%s): %s", name, host, e)

        if not all_ok:
            logger.info("检测到网络问题，建议检查代理/VPN 设置")
            # 注意：这里没法真正重置系统网络，但能报告问题
        return all_ok

    async def _fix_log_overflow(self) -> bool:
        """清理过大的日志文件"""
        log_dir = Path.home() / ".openscaw" / "logs"
        if not log_dir.exists():
            log_dir.mkdir(parents=True, exist_ok=True)
            return True

        rotated = 0
        for f in log_dir.glob("*.log*"):
            try:
                if f.stat().st_size > 5 * 1024 * 1024:  # > 5MB
                    backup = f.with_suffix(f.suffix + ".old")
                    f.rename(backup)
                    rotated += 1
                    logger.info("已轮转日志: %s (%.1fMB)", f.name, f.stat().st_size / 1024 / 1024)
            except Exception as e:
                logger.error("轮转日志失败 %s: %s", f, e)

        return rotated > 0

    async def _fix_no_response(self) -> bool:
        """修复无响应 - 发送ping或轻量请求"""
        process = self._find_openclaw_process()
        if not process:
            return False

        # 方法1: 发送 SIGCONT (继续被暂停的进程)
        try:
            os.kill(process.pid, signal.SIGCONT)
            logger.info("已发送 SIGCONT 到 PID %d", process.pid)
        except:
            pass

        # 方法2: 测试 API 是否恢复
        for _ in range(3):
            await asyncio.sleep(1)
            client = self.api_manager.get_client()
            if client:
                result = client.test_connection(timeout=3)
                if result.status.value == "healthy":
                    return True

        # 方法3: 检查网络
        await self._fix_network_issue()
        return False
    
    async def _fix_memory_high(self) -> bool:
        """修复内存过高"""
        process = self._find_openclaw_process()
        if not process:
            return False
        
        # 方法1: 尝试垃圾回收（如果是 Python 进程）
        try:
            os.kill(process.pid, signal.SIGUSR2)  # 某些框架使用 SIGUSR2 触发 GC
        except:
            pass
        
        # 方法2: 重启
        await asyncio.sleep(1)
        if process.memory_info().rss > self.config.get_monitor_config().memory_threshold_mb * 2 * 1024 * 1024:
            return await self._fix_process_stuck()
        
        return True
    
    def _find_openclaw_process(self):
        """查找 OpenClaw 进程"""

        patterns = [r"openclaw", r"claude-code", r"opencode", r"hermes.*agent"]
        
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                name = proc.info['name'] or ""
                cmdline = ' '.join(proc.info['cmdline'] or [])
                
                for pattern in patterns:
                    if re.search(pattern, name, re.IGNORECASE) or \
                       re.search(pattern, cmdline, re.IGNORECASE):
                        return psutil.Process(proc.info['pid'])
            except:
                continue
        
        return None
    
    async def _restart_openclaw(self) -> bool:
        """重新启动 OpenClaw"""
        # 尝试多种启动方式
        start_commands = [
            ["openclaw"],
            ["python", "-m", "openclaw"],
            ["npx", "openclaw"],
            ["claude-code"],
            ["opencode"],
        ]
        
        for cmd in start_commands:
            try:
                result = subprocess.run(
                    ["which", cmd[0]],
                    capture_output=True,
                    text=True
                )
                if result.returncode == 0:
                    subprocess.Popen(
                        cmd,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True
                    )
                    logger.info(f"已尝试启动: {' '.join(cmd)}")
                    await asyncio.sleep(3)
                    return self._find_openclaw_process() is not None
            except:
                continue
        
        return False
    
    def get_history(self) -> List[Dict]:
        """获取修复历史"""
        return self._fix_history[-50:]  # 最近50条
    
    def reset_failure_count(self, issue: str = None):
        """重置失败计数"""
        if issue:
            self._consecutive_failures[issue] = 0
        else:
            self._consecutive_failures.clear()
