"""CLI command: qitos init - Initialize a new project"""

import os
import sys
from typing import Dict, TextIO


TEMPLATE_FILES: Dict[str, str] = {
    "__init__.py": '''"""My Agent Project"""

__version__ = "0.1.0"
''',
    
    "agent.py": '''"""Agent implementation"""

from qitos import AgentModule, ToolRegistry, skill
from typing import List, Dict, Any


class MyAgent(AgentModule):
    """
    我的自定义 Agent
    
    在这里实现 perceive 和 update_context 方法
    """
    
    def __init__(self, toolkit, llm, **kwargs):
        super().__init__(
            toolkit=toolkit,
            llm=llm,
            system_prompt="你是一个智能助手，请帮助用户完成任务。",
            **kwargs
        )
    
    def perceive(self, context) -> List[Dict[str, str]]:
        """
        将当前 context 转换为 LLM 消息列表
        """
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": context.task}
        ]
        
        # 注入历史 observations
        for obs in context.observations:
            messages.append({"role": "user", "content": f"Observation: {obs}"})
        
        return messages
    
    def update_context(self, context, observations: List[Any]) -> None:
        """
        根据 observations 更新 context
        """
        # 默认行为已处理，这里可以添加自定义逻辑
        pass


def create_agent(toolkit, llm):
    """工厂函数：创建 Agent 实例"""
    return MyAgent(toolkit=toolkit, llm=llm)


if __name__ == "__main__":
    # 示例用法
    from qitos.core.skill import ToolRegistry
    
    # 创建工具
    toolkit = ToolRegistry()
    
    # 这里添加你的工具
    # toolkit.register(your_skill_function)
    
    # 创建 Agent（需要提供 llm）
    # agent = create_agent(toolkit, llm_function)
    # result = agent("你的任务")
    pass
''',
    
    "skills.py": '''"""Skill definitions"""

from qitos import skill
from typing import Dict, Any


@skill(domain="example")
def example_tool(param: str) -> Dict[str, Any]:
    """
    这是一个示例工具函数
    
    Args:
        param: 参数说明
        
    Returns:
        包含结果的字典
    """
    return {
        "status": "success",
        "message": f"工具执行成功，参数: {param}"
    }


@skill(domain="calculator")
def calculate(expression: str) -> Dict[str, Any]:
    """
    计算数学表达式
    
    Args:
        expression: 数学表达式，如 "2 + 3 * 4"
        
    Returns:
        计算结果
    """
    try:
        result = eval(expression)
        return {
            "status": "success",
            "result": result,
            "expression": expression
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }


# 在这里添加更多工具函数
# 每个工具都需要 @skill 装饰器
''',
    
    "prompts.py": '''"""Prompt templates"""

# 系统提示词模板
SYSTEM_PROMPT = """你是一个智能助手，请使用工具来帮助用户完成任务。

可用工具：
{tool_descriptions}

请根据用户的需求，选择合适的工具来完成任务。
"""

# 在这里定义你的提示词模板
# PROMPT_TEMPLATES = {
#     "default": "你是一个助手...",
#     "research": "你是一个研究员...",
# }
''',
    
    "config.yaml": '''# QitOS Agent Configuration

# LLM 配置
llm:
  provider: "openai"  # 或 "anthropic", "ollama" 等
  model: "gpt-4"
  api_key: "${OPENAI_API_KEY}"  # 使用环境变量
  
# Agent 配置
agent:
  max_steps: 10
  memory_window: 5
  error_strategy: "inject_error"
  
# 工具配置
tools:
  domain: "default"
  # 其他工具特定配置
''',
    
    "requirements.txt": '''# QitOS Framework
qitos>=3.1.0

# 可选：LLM 提供商
# openai>=1.0.0
# anthropic>=0.3.0
# ollama>=0.1.0

# 可选：依赖
# pyyaml>=6.0
''',
    
    "README.md": '''# My Agent Project

这是一个使用 QitOS Framework v3.1 构建的 Agent 项目。

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 运行 Agent
python agent.py
```

## 项目结构

- `agent.py`: Agent 主逻辑
- `skills.py`: 工具函数定义
- `prompts.py`: 提示词模板
- `config.yaml`: 配置文件

## 自定义

1. 在 `skills.py` 中添加你的工具函数
2. 在 `agent.py` 中修改 `perceive` 方法
3. 在 `config.yaml` 中配置 LLM
'''
}


def add_init_parser(subparsers):
    """添加 init 子命令到 parser"""
    parser = subparsers.add_parser(
        "init",
        help="初始化一个新项目",
        description="创建标准 QitOS 项目目录结构。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s my-agent          # 创建 my-agent 目录
  %(prog)s .                 # 在当前目录初始化
        """
    )
    
    parser.add_argument(
        "name",
        nargs="?",
        default="my-agent",
        help="项目名称 (默认: my-agent)"
    )
    
    parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="如果目录存在，强制覆盖"
    )
    
    parser.add_argument(
        "--no-git",
        action="store_true",
        help="不初始化 Git 仓库"
    )


def run_init(args) -> int:
    """运行 init 命令"""
    import argparse
    
    project_name = args.name
    force = args.force
    no_git = args.no_git
    
    # 确定项目路径
    if project_name == ".":
        project_path = os.getcwd()
        project_name = os.path.basename(project_path)
    else:
        project_path = os.path.join(os.getcwd(), project_name)
    
    # 检查目录是否存在
    if os.path.exists(project_path):
        if not force:
            print(f"❌ 错误: 目录 '{project_name}' 已存在")
            print("   使用 --force 强制覆盖")
            return 1
        else:
            print(f"⚠️  警告: 目录 '{project_name}' 已存在，将被覆盖")
    
    # 创建项目结构
    print(f"🚀 正在初始化项目: {project_name}")
    
    try:
        # 创建目录
        os.makedirs(project_path, exist_ok=True)
        
        # 创建文件
        for file_name, content in TEMPLATE_FILES.items():
            file_path = os.path.join(project_path, file_name)
            
            # 确保父目录存在
            parent_dir = os.path.dirname(file_path)
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            print(f"   ✅ 创建: {file_name}")
        
        # 初始化 Git
        if not no_git:
            git_path = os.path.join(project_path, '.git')
            if not os.path.exists(git_path):
                try:
                    import subprocess
                    subprocess.run(
                        ['git', 'init'],
                        cwd=project_path,
                        capture_output=True,
                        check=True
                    )
                    print(f"   ✅ 初始化 Git 仓库")
                except (subprocess.CalledProcessError, FileNotFoundError):
                    print(f"   ⚠️  Git 初始化失败（可能未安装 Git）")
        
        print(f"\n✅ 项目初始化完成!")
        print(f"\n📁 项目路径: {os.path.abspath(project_path)}")
        print(f"\n💡 下一步:")
        print(f"   cd {project_name}")
        print(f"   qitos play        # 启动交互式沙盒")
        print(f"   python agent.py  # 运行 Agent")
        
        return 0
    
    except Exception as e:
        print(f"❌ 错误: {e}")
        if hasattr(args, 'verbose') and args.verbose:
            import traceback
            traceback.print_exc()
        return 1
