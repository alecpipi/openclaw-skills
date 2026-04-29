#!/usr/bin/env python3
"""
OpenScaw - OpenClaw Guardian
本地 AI Agent 自动维护工具
"""

from setuptools import setup, find_packages
from pathlib import Path

# 读取 README
readme_path = Path(__file__).parent / "README.md"
long_description = readme_path.read_text(encoding='utf-8') if readme_path.exists() else ""

# 读取 requirements
requirements_path = Path(__file__).parent / "requirements.txt"
requirements = []
if requirements_path.exists():
    requirements = [
        line.strip() 
        for line in requirements_path.read_text(encoding='utf-8').split('\n') 
        if line.strip() and not line.startswith('#')
    ]

setup(
    name="openscaw",
    version="1.0.0",
    author="OpenScaw Team",
    author_email="",
    description="自动监控和修复本地 AI Agent 的智能守护工具",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/openscaw",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Tools",
        "Topic :: System :: Monitoring",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.8",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "openscaw=openscaw.cli:main",
        ],
    },
    include_package_data=True,
    package_data={
        "openscaw": ["*.yaml", "*.yml"],
    },
    keywords="openclaw ai agent guardian monitor fix repair kimi deepseek minimax",
    project_urls={
        "Bug Reports": "https://github.com/yourusername/openscaw/issues",
        "Source": "https://github.com/yourusername/openscaw",
        "Documentation": "https://github.com/yourusername/openscaw/blob/main/README.md",
    },
)