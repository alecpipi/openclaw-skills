# 🦜 OpenScaw - OpenClaw Guardian

[![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

> **自动监控和修复本地 AI Agent 的智能守护工具**

OpenScaw 是专为本地 AI Agent (如 OpenClaw、Claude Code、OpenCode 等) 设计的智能维护工具。它能够自动监控、诊断并修复各种常见问题，让你的 AI 助手始终保持最佳状态。

## ✨ 主要功能

- 📊 **实时监控** - 监控进程状态、API 健康、上下文长度、响应时间
- 🛠️ **智能修复** - 自动处理上下文过长、API Key 失效、进程卡死等问题
- 🔍 **深度诊断** - 分析日志、定位根因、生成详细报告
- 🚀 **多 API 支持** - Kimi、DeepSeek、MiniMax 等国内大模型
- 📢 **多种通知** - 控制台、Webhook、Slack、Telegram
- 🎨 **状态仪表盘** - 精美的终端状态显示

## 🚀 快速开始

### 安装

```bash
# 从 PyPI 安装
pip install openscaw

# 或者从源码安装
git clone https://github.com/yourusername/openscaw.git
cd openscaw
pip install -e .
```

### 配置 API Key

```bash
# 配置你的 API Key（至少需要一个）
export KIMI_API_KEY="your-kimi-api-key"
export DEEPSEEK_API_KEY="your-deepseek-api-key"
export MINIMAX_API_KEY="your-minimax-api-key"
```

### 基本使用

```bash
# 初始化
openscaw init

# 执行一次健康检查
openscaw check

# 启动持续监控
openscaw monitor

# 测试所有 API 连接
openscaw test
```

## 📚 完整命令手册

### 监控命令

```bash
# 启动持续监控
openscaw monitor

# 监控并自动修复问题
openscaw monitor --fix

# 设置检查间隔（秒）
openscaw monitor --interval 60
```

### 检查命令

```bash
# 基本检查
openscaw check

# JSON 格式输出
openscaw check --json

# 或
openscaw check --format json
```

### 修复命令

```bash
# 自动检测并修复所有问题
openscaw fix --auto

# 修复特定问题
openscaw fix context     # 修复上下文过长
openscaw fix api         # 修复 API Key 问题
openscaw fix process     # 修复进程卡死
openscaw fix memory      # 修复内存问题

# 修复所有可能的问题
openscaw fix all
```

### 诊断命令

```bash
# 深度诊断并生成报告
openscaw doctor

# 输出到文件
openscaw doctor -o report.md

# 生成状态报告
openscaw report -o status.md
```

### API 测试

```bash
# 测试所有配置的 API
openscaw test

# 测试特定 API
openscaw test --api kimi
openscaw test --api deepseek
openscaw test --api minimax
```

### 配置管理

```bash
# 查看配置
openscaw config --show

# 编辑配置
openscaw config --edit

# 设置配置项
openscaw config --set check_interval 60
```

### 其他命令

```bash
# 显示状态仪表盘
openscaw dashboard
openscaw status

# 查看日志
openscaw logs
openscaw logs -f              # 实时追踪
openscaw logs -n 100          # 显示最后100行

# 版本信息
openscaw version
```

## 🏠 配置文件

配置文件位于 `~/.openscaw/config.yaml`：

```yaml
monitor:
  check_interval: 30          # 检查间隔（秒）
  max_context_tokens: 8000    # 上下文最大 token 数
  response_timeout: 10        # 响应超时（秒）
  memory_threshold_mb: 2048   # 内存阈值（MB）
  cpu_threshold_percent: 80   # CPU 阈值（%）

fix_strategies:
  context_overflow:
    enabled: true
    threshold: 7000
  api_key_invalid:
    enabled: true
    max_retries: 3
  process_stuck:
    enabled: true
    graceful_timeout: 5

notifications:
  enabled: true
  channels: ["console"]
  notify_on: ["critical", "fix_failed"]
```

## 📁 项目结构

```
openscaw/
├── openscaw/
│   ├── __init__.py
│   ├── cli.py              # 命令行接口
│   ├── config.py           # 配置管理
│   ├── monitor.py          # 监控核心
│   ├── fixer.py            # 自动修复
│   ├── diagnostics.py      # 诊断引擎
│   ├── notifier.py         # 通知系统
│   └── api_client.py       # API 客户端
├── tests/
├── config/
├── scripts/
├── .github/workflows/
├── README.md
├── setup.py
├── requirements.txt
└── LICENSE
```

## 🛠️ 自动修复策略

| 问题 | 检测方式 | 自动修复 | 备注 |
|------|---------|---------|------|
| 上下文过长 | 监控 token 数 | 压缩/清理历史 | 保留最近10条消息 |
| API Key 失效 | 401 错误 | 切换到备用 Key | 支持多 Key 轮询 |
| 进程卡死 | 响应超时 | 重启进程 | 优雅终止后重启 |
| 无响应 | 心跳检测 | 发送唤醒信号 | 多次失败则重启 |
| 内存泄漏 | 内存监控 | 触发 GC 或重启 | 设置阈值保护 |

## 📖 支持的 AI Agent

OpenScaw 可以监控以下类型的本地 AI Agent：

- **OpenClaw** - 本项目主要目标
- **Claude Code** - Anthropic 的 CLI 工具
- **OpenCode** - 类似的开源 AI 编码助手
- **Aider** - AI 编程助手
- **Hermes Agent** - 通用 AI Agent 框架

## 🔧 开发

```bash
# 克隆仓库
git clone https://github.com/yourusername/openscaw.git
cd openscaw

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate  # Windows

# 安装开发依赖
pip install -e ".[dev]"

# 运行测试
pytest

# 格式化代码
black openscaw/
```

## 📤 GitHub Actions 集成

在 `.github/workflows/openscaw.yml` 添加：

```yaml
name: OpenScaw Health Check

on:
  schedule:
    - cron: '*/10 * * * *'  # 每10分钟检查
  workflow_dispatch:

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      
      - name: Install OpenScaw
        run: pip install openscaw
      
      - name: Run Health Check
        env:
          KIMI_API_KEY: ${{ secrets.KIMI_API_KEY }}
          DEEPSEEK_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}
        run: |
          openscaw check --format json > health_report.json
          cat health_report.json
      
      - name: Upload Report
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: health-report
          path: health_report.json
```

## 📋 TODO

- [ ] 支持更多 API (智谱 AI、通义千问等)
- [ ] Web 仪表盘
- [ ] 定制化修复脚本
- [ ] Docker 部署
- [ ] 更多通知渠道 (Email、企业微信等)
- [ ] 历史数据存储和分析

## 📜 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件

## 🙏 致谢

感谢以下提供 API 服务的厂商：

- [Moonshot AI](https://www.moonshot.cn/) (Kimi)
- [DeepSeek](https://www.deepseek.com/)
- [MiniMax](https://www.minimaxi.com/)

---

<p align="center">
  Made with ❤️ by OpenScaw Team
</p>