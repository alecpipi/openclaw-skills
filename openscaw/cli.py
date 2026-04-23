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
from pathlib import Path
from datetime import datetime
from typing import Optional

# 添加父目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from openscaw import __version__, __description__
from openscaw.config import ConfigManager
from openscaw.monitor import OpenClawMonitor, HealthLevel
from openscaw.fixer import AutoFixer, FixResult
from openscaw.diagnostics import DiagnosticsEngine
from openscaw.notifier import Notifier, StatusDashboard, NotifyLevel
from openscaw.api_client import APIClientManager

# 配置日志
log_dir = Path.home() / ".openscaw"
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_dir / "openscaw.log", mode='a')
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
  openscaw fix context       修复上下文过长问题
  openscaw fix api           修复 API Key 问题
  openscaw doctor            深度诊断并生成报告
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
                               choices=['context', 'api', 'process', 'memory', 'all'],
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
                                  'process_stuck', 'memory_high']:
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
        """医生命令 - 深度诊断"""
        print("👨‍⚕️ OpenScaw 正在诊断...\n")
        
        # 收集症状
        self.monitor = OpenClawMonitor(self.config)
        report = await self.monitor.check_health()
        
        symptoms = {
            "errors": report.errors,
            "api_status": report.api_status,
            "context_tokens": report.context_tokens,
            "memory_mb": report.process.memory_mb if report.process else 0,
            "response_time_ms": report.response_time_ms,
            "recent_changes": []  # 可从配置文件修改时间获取
        }
        
        # 执行诊断
        diagnosis = self.diagnostics.diagnose(symptoms)
        
        # 生成报告
        report_text = self.diagnostics.generate_report(diagnosis, symptoms)
        
        if args.output:
            Path(args.output).write_text(report_text, encoding='utf-8')
            print(f"报告已保存到: {args.output}")
        
        print(report_text)
        
        return 0 if diagnosis.confidence > 0.7 else 1
    
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


def main():
    """入口函数"""
    cli = OpenScawCLI()
    return cli.run()


if __name__ == '__main__':
    sys.exit(main())
