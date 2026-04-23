"""
通知系统 - 告警和状态通知
"""
import os
import json
import asyncio
import logging
from typing import List, Dict, Optional
from datetime import datetime
from enum import Enum
import requests

logger = logging.getLogger(__name__)

class NotifyLevel(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

class Notifier:
    """通知管理器 - 支挅多种通知渠道"""
    
    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.channels = self.config.get("notifications", {}).get("channels", ["console"])
        self.webhook_url = self.config.get("notifications", {}).get("webhook_url")
        self.notify_on = self.config.get("notifications", {}).get("notify_on", ["critical", "fix_failed"])
        
        self._history: List[Dict] = []
        self._rate_limits: Dict[str, datetime] = {}
    
    async def notify(self, message: str, level: NotifyLevel = NotifyLevel.INFO,
                    context: Dict = None):
        """发送通知
        
        Args:
            message: 通知消息
            level: 通知级别
            context: 额外上下文
        """
        # 检查是否需要通知
        if not self._should_notify(level):
            return
        
        # 检查频率限制
        if not self._check_rate_limit(level):
            logger.debug(f"通知被频率限制: {level.value}")
            return
        
        notification = {
            "timestamp": datetime.now().isoformat(),
            "level": level.value,
            "message": message,
            "context": context or {}
        }
        
        # 发送到各个渠道
        tasks = []
        for channel in self.channels:
            handler = getattr(self, f"_send_{channel}", None)
            if handler:
                tasks.append(handler(notification))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        
        # 记录历史
        self._history.append(notification)
        if len(self._history) > 100:
            self._history = self._history[-100:]
    
    def _should_notify(self, level: NotifyLevel) -> bool:
        """检查该级别是否需要通知"""
        level_priority = {
            NotifyLevel.INFO: 1,
            NotifyLevel.WARNING: 2,
            NotifyLevel.ERROR: 3,
            NotifyLevel.CRITICAL: 4
        }
        
        # 转换配置中的级别
        min_priority = 4  # 默认只通知严重问题
        for l in self.notify_on:
            if l in level_priority:
                min_priority = min(min_priority, level_priority[NotifyLevel(l)])
        
        return level_priority.get(level, 1) >= min_priority
    
    def _check_rate_limit(self, level: NotifyLevel) -> bool:
        """检查是否超出频率限制"""
        now = datetime.now()
        key = level.value
        
        # 各级别的最小间隔（秒）
        intervals = {
            NotifyLevel.INFO: 300,      # 5分钟
            NotifyLevel.WARNING: 60,    # 1分钟
            NotifyLevel.ERROR: 30,      # 30秒
            NotifyLevel.CRITICAL: 0     # 无限制
        }
        
        last_sent = self._rate_limits.get(key)
        if last_sent:
            interval = intervals.get(level, 60)
            if (now - last_sent).total_seconds() < interval:
                return False
        
        self._rate_limits[key] = now
        return True
    
    async def _send_console(self, notification: Dict):
        """发送到控制台"""
        level_icons = {
            "info": "ℹ️ ",
            "warning": "⚠️ ",
            "error": "❌ ",
            "critical": "🚨 "
        }
        
        icon = level_icons.get(notification["level"], "")
        print(f"[{notification['timestamp']}] {icon}{notification['message']}")
    
    async def _send_webhook(self, notification: Dict):
        """发送到 Webhook"""
        if not self.webhook_url:
            return
        
        try:
            response = requests.post(
                self.webhook_url,
                json=notification,
                timeout=10,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            logger.info("已发送到 webhook")
        except Exception as e:
            logger.error(f"Webhook 发送失败: {e}")
    
    async def _send_slack(self, notification: Dict):
        """发送到 Slack"""
        slack_webhook = os.getenv("SLACK_WEBHOOK_URL")
        if not slack_webhook:
            return
        
        color_map = {
            "info": "#36a64f",
            "warning": "#ff9900",
            "error": "#ff0000",
            "critical": "#990000"
        }
        
        payload = {
            "attachments": [{
                "color": color_map.get(notification["level"], "#808080"),
                "title": f"OpenScaw 通知 - {notification['level'].upper()}",
                "text": notification["message"],
                "footer": "OpenScaw Guardian",
                "ts": int(datetime.now().timestamp())
            }]
        }
        
        try:
            requests.post(slack_webhook, json=payload, timeout=10)
        except Exception as e:
            logger.error(f"Slack 发送失败: {e}")
    
    async def _send_telegram(self, notification: Dict):
        """发送到 Telegram"""
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        
        if not bot_token or not chat_id:
            return
        
        emoji_map = {
            "info": "ℹ️",
            "warning": "⚠️",
            "error": "❌",
            "critical": "🚨"
        }
        
        emoji = emoji_map.get(notification["level"], "")
        text = f"{emoji} <b>OpenScaw {notification['level'].upper()}</b>\n\n{notification['message']}"
        
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML"
        }
        
        try:
            requests.post(url, json=payload, timeout=10)
        except Exception as e:
            logger.error(f"Telegram 发送失败: {e}")
    
    def get_history(self, level: NotifyLevel = None, limit: int = 50) -> List[Dict]:
        """获取通知历史"""
        history = self._history
        if level:
            history = [h for h in history if h["level"] == level.value]
        return history[-limit:]
    
    def clear_history(self):
        """清空历史"""
        self._history.clear()


class StatusDashboard:
    """简易状态仪表盘"""
    
    def __init__(self):
        self.current_status = "unknown"
        self.last_check = None
        self.metrics = {}
    
    def update(self, report):
        """更新状态"""
        self.current_status = report.level.value
        self.last_check = datetime.now()
        self.metrics = {
            "pid": report.process.pid if report.process else None,
            "memory_mb": report.process.memory_mb if report.process else 0,
            "context_tokens": report.context_tokens,
            "response_time_ms": report.response_time_ms,
            "error_count": len(report.errors)
        }
    
    def render(self) -> str:
        """渲染简易仪表盘"""
        lines = [
            "╔" + "═" * 58 + "╗",
            "║" + "              OpenScaw 状态仪表盘".center(56) + "║",
            "╠" + "═" * 58 + "╣",
        ]
        
        # 状态指示
        status_icons = {
            "healthy": "🟢 健康",
            "warning": "🟡 警告",
            "critical": "🔴 严重",
            "unknown": "⚪ 未知"
        }
        status_str = status_icons.get(self.current_status, self.current_status)
        lines.append(f"║  状态: {status_str:<50}║")
        
        # 最后检查时间
        if self.last_check:
            time_str = self.last_check.strftime("%Y-%m-%d %H:%M:%S")
            lines.append(f"║  最后检查: {time_str:<46}║")
        
        lines.append("║" + " " * 58 + "║")
        
        # 指标
        if self.metrics:
            lines.append(f"║  进程ID: {str(self.metrics.get('pid', 'N/A')):<48}║")
            lines.append(f"║  内存: {self.metrics.get('memory_mb', 0):.1f} MB{' ':<42}║")
            lines.append(f"║  上下文: {self.metrics.get('context_tokens', 0)} tokens{' ':<39}║")
            lines.append(f"║  响应: {self.metrics.get('response_time_ms', 0):.0f} ms{' ':<43}║")
            lines.append(f"║  错误: {self.metrics.get('error_count', 0)}{' ':<51}║")
        
        lines.append("╚" + "═" * 58 + "╝")
        
        return "\n".join(lines)
