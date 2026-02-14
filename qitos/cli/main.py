#!/usr/bin/env python3
"""
QitOS CLI 主入口

支持以下命令：
- init: 初始化项目
- play: 交互式沙盒
- replay: 重放执行轨迹
- list-tools: 列出可用工具
"""

import sys
import argparse
from typing import List


def create_parser():
    """创建命令行参数解析器"""
    parser = argparse.ArgumentParser(
        prog="qitos",
        description="🧘 QitOS Framework v3.1 - 为开发者幸福感而生的状态驱动 Agent 框架",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s init my-agent          # 初始化新项目
  %(prog)s play                   # 启动交互式沙盒
  %(prog)s replay trace.json      # 重放执行轨迹
  %(prog)s list-tools            # 列出可用工具
        """
    )
    
    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s v3.1.0"
    )
    
    parser.add_argument(
        "--verbose",
        "-v",
        action="count",
        default=0,
        help="详细输出 (可叠加使用)"
    )
    
    subparsers = parser.add_subparsers(
        title="命令",
        dest="command",
        description="可用命令"
    )
    
    # init 命令
    from .init import add_init_parser
    add_init_parser(subparsers)
    
    # play 命令
    from .play import add_play_parser
    add_play_parser(subparsers)
    
    # replay 命令
    from .replay import add_replay_parser
    add_replay_parser(subparsers)
    
    # list-tools 命令
    add_list_tools_parser(subparsers)
    
    return parser


def add_list_tools_parser(subparsers):
    """添加 list-tools 子命令"""
    parser = subparsers.add_parser(
        "list-tools",
        help="列出项目中的可用工具",
        description="扫描项目中的 @skill 装饰器，生成可读的工具列表。"
    )
    
    parser.add_argument(
        "--path",
        "-p",
        default=".",
        help="项目路径 (默认: 当前目录)"
    )
    
    parser.add_argument(
        "--format",
        "-f",
        choices=["text", "json"],
        default="text",
        help="输出格式 (默认: text)"
    )


def main(args: List[str] = None):
    """CLI 主入口"""
    if args is None:
        args = sys.argv[1:]
    
    parser = create_parser()
    parsed_args = parser.parse_args(args)
    
    # 根据命令分发
    command = parsed_args.command
    
    if command is None:
        parser.print_help()
        print("\n💡 提示: 使用 %(prog)s play 启动交互式沙盒")
        return 0
    
    # 命令分发
    try:
        if command == "init":
            from .init import run_init
            return run_init(parsed_args)
        
        elif command == "play":
            from .play import run_play
            return run_play(parsed_args)
        
        elif command == "replay":
            from .replay import run_replay
            return run_replay(parsed_args)
        
        elif command == "list-tools":
            return run_list_tools(parsed_args)
        
        else:
            parser.print_help()
            return 1
    
    except KeyboardInterrupt:
        print("\n👋 用户中断")
        return 130
    
    except Exception as e:
        if parsed_args.verbose:
            import traceback
            traceback.print_exc()
        else:
            print(f"❌ 错误: {e}", file=sys.stderr)
        return 1


def run_list_tools(args):
    """运行 list-tools 命令"""
    import os
    import json
    from qitos.core.skills import skill, ToolRegistry
    
    # 扫描路径
    path = os.path.abspath(args.path)
    
    if not os.path.exists(path):
        print(f"❌ 路径不存在: {path}")
        return 1
    
    # 收集工具函数
    skills = []
    
    if os.path.isfile(path) and path.endswith('.py'):
        # 单个文件
        module_name = os.path.splitext(os.path.basename(path))[0]
        import importlib.util
        spec = importlib.util.spec_from_file_location(module_name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if callable(attr) and hasattr(attr, '_is_skill') and attr._is_skill:
                skills.append(attr)
    
    elif os.path.isdir(path):
        # 目录：扫描所有 .py 文件
        for root, dirs, files in os.walk(path):
            for file in files:
                if file.endswith('.py') and not file.startswith('_'):
                    file_path = os.path.join(root, file)
                    module_name = os.path.splitext(os.path.basename(file_path))[0]
                    
                    try:
                        import importlib.util
                        spec = importlib.util.spec_from_file_location(module_name, file_path)
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                        
                        for attr_name in dir(module):
                            attr = getattr(module, attr_name)
                            if callable(attr) and hasattr(attr, '_is_skill') and attr._is_skill:
                                skills.append(attr)
                    except Exception as e:
                        if args.verbose:
                            print(f"⚠️ 跳过 {file_path}: {e}")
    
    # 生成输出
    if args.format == "json":
        output = {
            "tool_count": len(skills),
            "tools": [
                {
                    "name": s.__name__,
                    "domain": getattr(s, '_domain', 'default'),
                    "doc": (s.__doc__ or "").split('\n')[0]
                }
                for s in skills
            ]
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        # 文本格式
        print(f"🧰 找到 {len(skills)} 个可用工具:\n")
        
        if not skills:
            print("  未找到 @skill 装饰的函数")
            print("  提示: 使用 @skill(domain='xxx') 装饰你的工具函数")
            return 0
        
        for skill_func in skills:
            domain = getattr(skill_func, '_domain', 'default')
            doc = (skill_func.__doc__ or "").split('\n')[0] or "无描述"
            
            print(f"## {skill_func.__name__} [{domain}]")
            print(f"   {doc}\n")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
