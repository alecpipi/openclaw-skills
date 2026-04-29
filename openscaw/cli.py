#!/usr/bin/env python3
"""
OpenScaw CLI - 命仄行接口
"""
import os
import sys
import json
import asyncio
import argparse
import logging
import io
from pathlib import Path
from datetime import datetime
from typing import Optional

# 添加父目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from openscaw import __version__, __description__
from openscaw.config import ConfigManager
from openscaw.monitor import OpenClawMonitor, HealthLevel
from openscaw.fixer import AutoFixer, FixResult
from openscaw.diagnostics import DiagnosticsEngine, LogDiscoverer
from openscaw.notifier import Notifier, StatusDashboard, NotifyLevel
from openscaw.api_client import APIClientManager

# 配置日志
def _setup_console():
    """Configure stdout/stderr to handle Unicode on all platforms (fixes GBK crash on Windows)."""
    if sys.platform == 'win32':
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')

_setup_console()

log_dir = Path.home() / ".openscaw"
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_dir / "openscaw.log", mode='a', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


class OpenScawCLI:
    """OpenScaw 命令行工具"""
    
    def __init__(self):
        self.config = ConfigManager()
        self.monitor: Optional[OpenClawMonitor] = None
        self.fixer: Optional[AutoFixer] = None
        self.diagnostics = DiagnosticsEngine()
        self.log_discoverer = LogDiscoverer()
        self.notifier = Notifier(self.config.config)
        self.dashboard = StatusDashboard()
        self.api_manager = APIClientManager()
    
    def run(self, args=None):
        """运行 CLI"""
        parser = self._create_parser()
        parsed_args = parser.parse_args(args)
        
        if not parsed_args.command:
            parser.print_help()
            return 0
        
        # 设置日志级别
        if parsed_args.verbose:
            logging.getLogger().setLevel(logging.DEBUG)
        
        # 执行命令
        command_map = {
            'init': self.cmd_init,
            'monitor': self.cmd_monitor,
            'check': self.cmd_check,
            'fix': self.cmd_fix,
            'config': self.cmd_config,
            'test': self.cmd_test,
            'doctor': self.cmd_doctor,
            'report': self.cmd_report,
            'dashboard': self.cmd_dashboard,
            'status': self.cmd_status,
            'logs': self.cmd_logs,
            'version': self.cmd_version,
            'revive': self.cmd_revive,
        }
        
        handler = command_map.get(parsed_args.command)
        if handler:
            try:
                return asyncio.run(handler(parsed_args))
            except KeyboardInterrupt:
                print("\n⚠️ 用户中断")
                return 130
            except Exception as e:
                logger.exception("命令执行失败")
                print(f"❌ 错误: {e}")
                return 1
        else:
            print(f"未知命令: {parsed_args.command}")
            return 1
    
    def _create_parser(self) -> argparse.ArgumentParser:
        """创建命令解析器"""
        parser = argparse.ArgumentParser(
            prog='openscaw',
            description=__description__,
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
示例:
  openscaw init              初始化配置
  openscaw check             执行一次健康检查
  openscaw monitor           启动持续监控
  openscaw revive            抢救卡死的 OpenClaw 进程
  openscaw fix context       修复上下文过长问题
  openscaw fix api           修复 API Key 问题
  openscaw doctor            深度诊断并生成报告（含日志分析）
  openscaw test              测试所有 API 连接
  openscaw dashboard         显示状态仪表盘
            """
        )
        
        parser.add_argument('-v', '--verbose', action='store_true',
                           help='详细输出')
        parser.add_argument('--version', action='version', 
                           version=f'%(prog)s {__version__}')
        
        subparsers = parser.add_subparsers(dest='command', help='可用命令')
        
        # init
        init_parser = subparsers.add_parser('init', help='初始化 OpenScaw 配置')
        init_parser.add_argument('--openclaw-path', help='OpenClaw 安装路径')
        
        # monitor
        monitor_parser = subparsers.add_parser('monitor', help='启动持续监控')
        monitor_parser.add_argument('--interval', type=int, help='检查间隔(秒)')
        monitor_parser.add_argument('--fix', action='store_true', help='自动修复问题')
        
        # check
        check_parser = subparsers.add_parser('check', help='执行一次健康检查')
        check_parser.add_argument('--json', action='store_true', help='JSON 格式输出')
        check_parser.add_argument('--format', choices=['text', 'json'], default='text')
        
        # fix
        fix_parser = subparsers.add_parser('fix', help='执行修复')
        fix_parser.add_argument('issue', nargs='?',
                               choices=['context', 'api', 'process', 'memory', 'network', 'zombie', 'all'],
                               help='要修复的问题')
        fix_parser.add_argument('--auto', action='store_true', help='自动修复所有问题')
        
        # config
        config_parser = subparsers.add_parser('config', help='管理配置')
        config_parser.add_argument('--edit', action='store_true', help='编辑配置文件')
        config_parser.add_argument('--show', action='store_true', help='显示当前配置')
        config_parser.add_argument('--set', nargs=2, metavar=('KEY', 'VALUE'),
                                  help='设置配置项')
        
        # test
        test_parser = subparsers.add_parser('test', help='测试 API 连接')
        test_parser.add_argument('--api', choices=['kimi', 'deepseek', 'minimax', 'all'],
                                default='all', help='指定测试的 API')
        
        # doctor
        doctor_parser = subparsers.add_parser('doctor', help='深度诊断并生成报告')
        doctor_parser.add_argument('--output', '-o', help='输出报告文件路径')
        
        # report
        report_parser = subparsers.add_parser('report', help='生成状态报告')
        report_parser.add_argument('--output', '-o', help='输出报告文件路径')
        
        # dashboard
        dashboard_parser = subparsers.add_parser('dashboard', help='显示状态仪表盘')
        
        # status
        status_parser = subparsers.add_parser('status', help='显示当前状态')
        
        # logs
        logs_parser = subparsers.add_parser('logs', help='查看日志')
        logs_parser.add_argument('--follow', '-f', action='store_true', help='实时追踪日志')
        logs_parser.add_argument('--lines', '-n', type=int, default=50, help='显示行数')
        
        # version
        version_parser = subparsers.add_parser('version', help='显示版本信息')

        # revive
        revive_parser = subparsers.add_parser('revive', help='抢救卡死的 OpenClaw 进程（自动诊断+修复+重启）')
        revive_parser.add_argument('--force', action='store_true',
                                   help='强制重启（不尝试恢复）')
        revive_parser.add_argument('--restart-only', action='store_true',
                                   help='仅重启，不做诊断')

        return parser
    
    async def cmd_init(self, args) -> int:
        """初始化命令"""
        print("🚀 初始化 OpenScaw...")
        
        # 创建配置目录
        config_dir = Path.home() / ".openscaw"
        config_dir.mkdir(exist_ok=True)
        
        # 检查环境变量
        apis_to_check = ['KIMI_API_KEY', 'DEEPSEEK_API_KEY', 'MINIMAX_API_KEY']
        print("\n🔐 检查 API Key 配置:")
        for api_env in apis_to_check:
            value = os.getenv(api_env)
            status = "✅ 已配置" if value else "❌ 未配置"
            print(f"   {api_env}: {status}")
        
        # 确保配置文件存在
        if not self.config.config_path.exists():
            self.config._create_default_config()
        
        print(f"\n📁 配置目录: {config_dir}")
        print(f"📋 配置文件: {self.config.config_path}")
        print("\n✅ 初始化完成!")
        print("\n快速开始:")
        print("  openscaw check    执行健康检查")
        print("  openscaw monitor  启动监控")
        print("  openscaw test     测试 API 连接")
        
        return 0
    
    async def cmd_monitor(self, args) -> int:
        """监控命令"""
        print("👁️  启动 OpenScaw 监控...")
        print("按 Ctrl+C 停止\n")
        
        self.monitor = OpenClawMonitor(self.config)
        self.fixer = AutoFixer(self.monitor, self.config)
        
        # 设置监控间隔
        if args.interval:
            self.monitor.monitor_cfg.check_interval = args.interval
        
        # 注册状态变化回调
        async def on_status_change(report):
            timestamp = report.timestamp.strftime("%H:%M:%S")
            icon = {
                HealthLevel.HEALTHY: "✅",
                HealthLevel.WARNING: "⚠️",
                HealthLevel.CRITICAL: "🚨"
            }.get(report.level, "❓")
            
            print(f"[{timestamp}] {icon} {report.level.value.upper()}")
            
            # 显示建议
            for suggestion in report.suggestions[:2]:
                print(f"      {suggestion}")
            
            # 自动修复
            if args.fix and report.level != HealthLevel.HEALTHY:
                print("      🛠️  正在自动修复...")
                results = await self.fixer.auto_fix(report)
                for fix_name, result in results.items():
                    print(f"         {fix_name}: {result.value}")
        
        self.monitor.register_callback(lambda r: asyncio.create_task(on_status_change(r)))
        
        # 启动监控
        try:
            await self.monitor.start()
        except KeyboardInterrupt:
            self.monitor.stop()
            print("\n监控已停止")
        
        return 0
    
    async def cmd_check(self, args) -> int:
        """检查命令"""
        print("🔍 执行健康检查...\n")
        
        self.monitor = OpenClawMonitor(self.config)
        report = await self.monitor.check_health()
        
        # 更新仪表盘
        self.dashboard.update(report)
        
        if args.json or args.format == 'json':
            # JSON 输出
            data = {
                "timestamp": report.timestamp.isoformat(),
                "status": report.level.value,
                "process": {
                    "pid": report.process.pid if report.process else None,
                    "name": report.process.name if report.process else None,
                    "memory_mb": report.process.memory_mb if report.process else 0,
                    "cpu_percent": report.process.cpu_percent if report.process else 0,
                },
                "api_status": report.api_status,
                "context_tokens": report.context_tokens,
                "response_time_ms": report.response_time_ms,
                "errors": report.errors,
                "suggestions": report.suggestions
            }
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            # 文本输出
            print(self.dashboard.render())
            print()
            
            if report.suggestions:
                print("💡 建议:")
                for suggestion in report.suggestions:
                    print(f"   {suggestion}")
            
            if report.errors:
                print("\n🐛 最近错误:")
                for error in report.errors[:3]:
                    print(f"   - {error[:100]}")
        
        # 返回码
        if report.level == HealthLevel.HEALTHY:
            return 0
        elif report.level == HealthLevel.WARNING:
            return 1
        else:
            return 2
    
    async def cmd_fix(self, args) -> int:
        """修复命令"""
        self.monitor = OpenClawMonitor(self.config)
        self.fixer = AutoFixer(self.monitor, self.config)
        
        if args.auto:
            # 自动模式 - 先检查再修复
            print("🔍 检查当前状态...")
            report = await self.monitor.check_health()
            
            if report.level == HealthLevel.HEALTHY:
                print("✅ 系统健康，无需修复")
                return 0
            
            print(f"⚠️ 检测到问题: {report.level.value}")
            print("🛠️  自动修复中...")
            
            results = await self.fixer.auto_fix(report)
            
            print("\n修复结果:")
            for fix_name, result in results.items():
                icon = "✅" if result == FixResult.SUCCESS else "❌"
                print(f"   {icon} {fix_name}: {result.value}")
            
            return 0 if any(r == FixResult.SUCCESS for r in results.values()) else 1
        
        elif args.issue:
            # 指定问题修复
            issue_map = {
                'context': 'context_overflow',
                'api': 'api_key_invalid',
                'process': 'process_stuck',
                'memory': 'memory_high',
                'network': 'network_issue',
                'zombie': 'zombie_process',
                'all': None
            }
            
            issue = issue_map.get(args.issue)
            
            if issue:
                print(f"🛠️  修复问题: {args.issue}")
                result = await self.fixer.fix(issue)
                print(f"结果: {result.value}")
                return 0 if result == FixResult.SUCCESS else 1
            elif args.issue == 'all':
                # 修复所有可能的问题
                print("🛠️  执行所有修复...")
                for issue_name in ['context_overflow', 'api_key_invalid',
                                  'network_issue', 'memory_high',
                                  'zombie_process', 'process_stuck']:
                    result = await self.fixer.fix(issue_name)
                    print(f"   {issue_name}: {result.value}")
                return 0
        
        else:
            print("请指定要修复的问题，使用 'openscaw fix --help' 查看帮助")
            return 1
    
    async def cmd_config(self, args) -> int:
        """配置命令"""
        if args.edit:
            self.config.edit()
            return 0
        
        if args.show:
            import yaml
            print(yaml.dump(self.config.config, allow_unicode=True, sort_keys=False))
            return 0
        
        if args.set:
            key, value = args.set
            # 简单设置（不支持嵌套）
            try:
                # 尝试解析为数值
                if value.isdigit():
                    value = int(value)
                elif value.lower() in ('true', 'false'):
                    value = value.lower() == 'true'
            except:
                pass
            
            self.config.config[key] = value
            self.config.save()
            print(f"✅ 设置 {key} = {value}")
            return 0
        
        # 默认显示配置信息
        print("📋 OpenScaw 配置")
        print(f"   配置文件: {self.config.config_path}")
        print(f"   检查间隔: {self.config.get_monitor_config().check_interval}秒")
        print(f"   上下文阈值: {self.config.get_monitor_config().max_context_tokens} tokens")
        print(f"   内存阈值: {self.config.get_monitor_config().memory_threshold_mb} MB")
        print("\n使用 '--edit' 编辑配置，'--show' 查看完整配置")
        return 0
    
    async def cmd_test(self, args) -> int:
        """测试命令"""
        print("🔹 测试 API 连接...\n")
        
        apis_to_test = ['kimi', 'deepseek', 'minimax'] if args.api == 'all' else [args.api]
        
        results = {}
        for api_name in apis_to_test:
            client = self.api_manager.get_client(api_name)
            if not client:
                print(f"   ❌ {api_name.upper()}: 未配置 API Key")
                continue
            
            print(f"   ⏳ 测试 {api_name.upper()}...", end=' ', flush=True)
            result = client.test_connection()
            results[api_name] = result
            
            icon = "✅" if result.status.value == "healthy" else "❌"
            print(f"{icon} {result.status.value} ({result.response_time_ms:.0f}ms)")
            
            if result.message and result.status.value != "healthy":
                print(f"      → {result.message}")
        
        # 总结
        healthy_count = sum(1 for r in results.values() if r.status.value == "healthy")
        total = len(results)
        print(f"\n测试结果: {healthy_count}/{total} 个 API 正常")
        
        return 0 if healthy_count == total else 1
    
    async def cmd_doctor(self, args) -> int:
        """医生命令 - 深度诊断（含日志分析）"""
        print("OpenScaw 正在诊断...\n")

        # 扫描日志
        print("--- 日志扫描 ---")
        logs = self.log_discoverer.discover_logs()
        active_log = self.log_discoverer.find_active_log(hours=2)
        if logs:
            print(f"   发现 {len(logs)} 个日志文件")
            for log in logs[:5]:
                age = self.log_discoverer.format_log_age(log)
                size = log.stat().st_size / 1024
                print(f"   - {log.name} ({size:.0f}KB, {age})")
            if active_log:
                print(f"\n   最近活跃: {active_log}")
        else:
            print("   未找到日志文件")
        print()

        # 收集症状
        self.monitor = OpenClawMonitor(self.config)
        report = await self.monitor.check_health()

        symptoms = {
            "errors": report.errors,
            "api_status": report.api_status,
            "context_tokens": report.context_tokens,
            "memory_mb": report.process.memory_mb if report.process else 0,
            "cpu_percent": report.process.cpu_percent if report.process else 0,
            "response_time_ms": report.response_time_ms,
            "process": report.process,
            "log_active": report.details.get("log_active"),
            "recent_changes": [],
        }

        # 日志分析
        print("--- 日志异常分析 ---")
        log_diag = None
        if active_log:
            log_lines = self.log_discoverer.tail_log(active_log, n_lines=300)
            log_diag = self.diagnostics.diagnose_from_logs(log_lines)
            if log_diag and log_diag.confidence >= 0.5:
                print(f"   根因: {log_diag.root_cause}")
                print(f"   置信度: {log_diag.confidence * 100:.0f}%")
                if log_diag.evidence:
                    for ev in log_diag.evidence[:3]:
                        print(f"   - {ev[:120]}")
            else:
                print("   日志中未发现明显异常")
        else:
            print("   无活跃日志可供分析")
        print()

        # 系统诊断
        print("--- 系统诊断 ---")
        diagnosis = self.diagnostics.diagnose(symptoms)

        # 综合报告：优先采纳日志分析结果
        if log_diag and log_diag.confidence >= 0.6:
            final_diag = log_diag
        else:
            final_diag = diagnosis

        report_text = self.diagnostics.generate_report(final_diag, symptoms)

        if args.output:
            Path(args.output).write_text(report_text, encoding='utf-8')
            print(f"报告已保存到: {args.output}")

        print(report_text)

        return 0 if final_diag.confidence > 0.7 else 1
    
    async def cmd_report(self, args) -> int:
        """报告命令"""
        print("📊 生成状态报告...\n")
        
        self.monitor = OpenClawMonitor(self.config)
        report = await self.monitor.check_health()
        
        lines = [
            "# OpenScaw 健康报告",
            "",
            f"生成时间: {report.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            f"状态: {report.level.value}",
            "",
            "## 进程信息",
        ]
        
        if report.process:
            lines.extend([
                f"- PID: {report.process.pid}",
                f"- 名称: {report.process.name}",
                f"- 内存: {report.process.memory_mb:.1f} MB",
                f"- CPU: {report.process.cpu_percent:.1f}%",
                f"- 运行时间: {report.process.created}",
            ])
        else:
            lines.append("进程未运行")
        
        lines.extend([
            "",
            "## API 状态",
        ])
        
        for api, status in report.api_status.items():
            lines.append(f"- {api}: {status}")
        
        lines.extend([
            "",
            f"## 上下文: {report.context_tokens} tokens",
            f"## 响应时间: {report.response_time_ms:.0f} ms",
            "",
            "## 建议",
        ])
        
        for suggestion in report.suggestions:
            lines.append(f"- {suggestion}")
        
        if report.errors:
            lines.extend([
                "",
                "## 错误",
            ])
            for error in report.errors:
                lines.append(f"```\n{error}\n```")
        
        report_text = "\n".join(lines)
        
        if args.output:
            Path(args.output).write_text(report_text, encoding='utf-8')
            print(f"报告已保存到: {args.output}")
        else:
            print(report_text)
        
        return 0
    
    async def cmd_dashboard(self, args) -> int:
        """仪表盘命令"""
        self.monitor = OpenClawMonitor(self.config)
        report = await self.monitor.check_health()
        self.dashboard.update(report)
        print(self.dashboard.render())
        return 0
    
    async def cmd_status(self, args) -> int:
        """状态命令"""
        return await self.cmd_dashboard(args)
    
    async def cmd_logs(self, args) -> int:
        """日志命令"""
        log_file = Path.home() / ".openscaw" / "openscaw.log"
        
        if not log_file.exists():
            print("日志文件不存在")
            return 1
        
        if args.follow:
            # 实时追踪
            print("正在追踪日志 (按 Ctrl+C 退出)...")
            import subprocess
            try:
                subprocess.run(["tail", "-f", str(log_file)])
            except KeyboardInterrupt:
                print()
        else:
            # 显示最后 n 行
            import subprocess
            subprocess.run(["tail", "-n", str(args.lines), str(log_file)])
        
        return 0
    
    async def cmd_version(self, args) -> int:
        """版本命令"""
        print(f"OpenScaw {__version__}")
        print(f"{__description__}")
        print("\n支持的 API:")
        print("  - Kimi (Moonshot AI)")
        print("  - DeepSeek")
        print("  - MiniMax")
        return 0

    async def cmd_revive(self, args) -> int:
        """抢救命令 — 当 OpenClaw 卡死/无响应时一键恢复"""
        print("+" + "=" * 58 + "+")
        print("|" + "        OpenScaw 抢救模式 — 恢复 OpenClaw 进程".ljust(58) + "|")
        print("+" + "=" * 58 + "+")
        print()

        self.monitor = OpenClawMonitor(self.config)
        self.fixer = AutoFixer(self.monitor, self.config)

        # ── Step 1: 检查进程 ──
        print("[1/5] 检查进程状态...")
        process = self.monitor._check_process()

        if process:
            print(f"   PID: {process.pid}")
            print(f"   名称: {process.name}")
            print(f"   状态: {process.status}")
            print(f"   内存: {process.memory_mb:.0f} MB")
            print(f"   CPU: {process.cpu_percent:.1f}%")

            if process.status == "zombie":
                print("   [!] 进程是僵尸状态，需强制清理")
            elif process.cpu_percent < 1 and process.memory_mb > 0:
                print("   [?] 进程 CPU 使用率极低，可能已挂起")
        else:
            print("   进程未运行")

        # ── Step 2: 查找并分析日志 ──
        print()
        print("[2/5] 扫描日志文件...")
        logs = self.log_discoverer.discover_logs()
        active_log = self.log_discoverer.find_active_log(hours=2)

        if logs:
            print(f"   发现 {len(logs)} 个日志文件")
            for log in logs[:5]:
                age = self.log_discoverer.format_log_age(log)
                size = log.stat().st_size / 1024
                print(f"   - {log.name} ({size:.0f}KB, {age})")
            if active_log:
                print(f"\n   最近活跃日志: {active_log.name}")
            else:
                print("\n   未发现近期活跃的日志文件")
        else:
            print("   未发现日志文件")

        if args.restart_only:
            print("\n   --restart-only 模式，跳过诊断直接重启")
            print("\n[3/5] 跳过诊断")
            print("[4/5] 跳过修复")
        else:
            # ── Step 3: 日志诊断 ──
            print()
            print("[3/5] 日志异常分析...")
            if active_log:
                log_lines = self.log_discoverer.tail_log(active_log, n_lines=200)
                diag = self.diagnostics.diagnose_from_logs(log_lines)
                if diag and diag.confidence >= 0.5:
                    print(f"   发现问题: {diag.root_cause}")
                    print(f"   置信度: {diag.confidence * 100:.0f}%")
                    if diag.evidence:
                        print("   证据:")
                        for ev in diag.evidence[:3]:
                            print(f"     - {ev[:120]}")
                    if diag.recommendations:
                        print("   建议:")
                        for rec in diag.recommendations[:3]:
                            print(f"     - {rec}")
                else:
                    print("   日志分析未发现明显异常模式")
            else:
                print("   无日志可供分析")

            # ── Step 4: 执行修复 ──
            print()
            print("[4/5] 执行恢复操作...")

            if process and not args.force:
                fixes_applied = False

                # 僵尸进程处理
                if process.status == "zombie":
                    print("   -> 清理僵尸进程...")
                    result = await self.fixer.fix("zombie_process")
                    print(f"      {result.value}")
                    fixes_applied = True

                # 唤醒尝试
                print("   -> 尝试唤醒进程...")
                result = await self.fixer.fix("no_response")
                print(f"      {result.value}")
                if result == FixResult.SUCCESS:
                    fixes_applied = True

                # 检查 API
                print("   -> 检查 API 连通性...")
                result = await self.fixer.fix("network_issue")
                if result == FixResult.FAILED:
                    print("      [提示] 网络可能不通，请检查代理/VPN 设置")
                else:
                    print("      网络正常")

                # 如果唤醒无效，重启
                if not fixes_applied:
                    print("   -> 唤醒无效，尝试重启进程...")
                    result = await self.fixer.fix("process_stuck")
                    print(f"      {result.value}")
            else:
                # 强制重启
                print("   -> 强制重启进程...")
                if process:
                    await self.fixer.fix("zombie_process")
                result = await self.fixer.fix("process_stuck")
                print(f"      {result.value}")

        # ── Step 5: 最终检查 ──
        print()
        print("[5/5] 验证恢复结果...")
        await asyncio.sleep(2)
        report = await self.monitor.check_health()

        if report.level == HealthLevel.HEALTHY:
            print("\n   [OK] OpenClaw 已成功恢复！")
            return 0
        elif report.level == HealthLevel.WARNING:
            print(f"\n   [!] 进程已恢复但存在警告:")
            for s in report.suggestions[:3]:
                print(f"     - {s}")
            return 1
        else:
            print("\n   [FAIL] 恢复失败，建议手动检查:")
            print("     1. 检查 OpenClaw 是否已安装")
            print("     2. 检查 API Key 环境变量")
            print("     3. 查看日志获取详细信息")
            return 2


def main():
    """入口函数"""
    cli = OpenScawCLI()
    return cli.run()


if __name__ == '__main__':
    sys.exit(main())
