"""Setup configuration for QitOS."""

from __future__ import annotations

import os
import re
from setuptools import find_packages, setup


def _read_version() -> str:
    here = os.path.abspath(os.path.dirname(__file__))
    init_path = os.path.join(here, "qitos", "__init__.py")
    with open(init_path, encoding="utf-8") as f:
        content = f.read()
    match = re.search(r'^__version__ = [\'"]([^\'"]+)[\'"]', content, re.M)
    if not match:
        raise RuntimeError("Cannot find __version__ in qitos/__init__.py")
    return match.group(1)


def _read_readme() -> str:
    here = os.path.abspath(os.path.dirname(__file__))
    readme_path = os.path.join(here, "README.md")
    with open(readme_path, encoding="utf-8") as f:
        return f.read()


setup(
    name="qitos",
    version=_read_version(),
    description="QitOS - research-oriented AgentModule + Engine framework",
    long_description=_read_readme(),
    long_description_content_type="text/markdown",
    author="QitOS Team",
    license="MIT",
    url="https://github.com/qitos/framework",
    packages=find_packages(exclude=["tests*", "examples*", "templates*", "docs*"]),
    python_requires=">=3.9",
    install_requires=[],
    extras_require={
        "models": ["openai>=1.0.0"],
        "yaml": ["pyyaml>=6.0"],
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=4.0.0",
            "black>=23.0.0",
            "flake8>=6.0.0",
            "mypy>=1.0.0",
        ],
        "all": ["openai>=1.0.0", "pyyaml>=6.0"],
    },
    include_package_data=True,
    zip_safe=False,
    entry_points={
        "console_scripts": [
            "qita=qitos.qita.cli:main",
        ]
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
)
