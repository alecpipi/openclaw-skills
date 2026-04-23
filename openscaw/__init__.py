"""
OpenScaw - OpenClaw Guardian
本地 AI Agent 自动维护工具
支持 Kimi、MiniMax、DeepSeek 等国内大模型
"""

__version__ = "1.0.0"
__author__ = "OpenScaw Team"
__description__ = "自动监控和修复本地 AI Agent 的智能守护工具"

from .monitor import OpenClawMonitor
from .fixer import AutoFixer
from .diagnostics import DiagnosticsEngine
from .notifier import Notifier

__all__ = [
    "OpenClawMonitor",
    "AutoFixer", 
    "DiagnosticsEngine",
    "Notifier"
]