#!/usr/bin/env python3
"""CLI command: qitos play - Interactive Sandbox"""

import os
import sys
import json
from typing import Optional


def add_play_parser(subparsers):
    """添加 play 子命令到 parser"""
    parser = subparsers.add_parser(
        "play",
        help="启动交互式沙盒",
        description="启动 REPL 环境，允许开发者介入 Agent 的每一步。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
命令:
  (text)        作为用户输入发送给 Agent
  :step         仅执行一步
  :ctx          打印当前 Context JSON
  :log          查看最近的 Mutation Log
  :undo         回滚到上一步
  :save <file>  保存当前现场快照
  :load <file>  加载现场快照
  :tools        列出可用工具
  :help         显示帮助
  :quit / :exit 退出

示例:
  %(prog)s                           # 使用默认配置
  %(prog)s --agent my_agent:ResearchAgent  # 指定 Agent
        """
    )
    
    parser.add_argument(
        "--agent",
        "-a",
        help="指定 Agent 模块 (格式: module:AgentClass)"
    )
    
    parser.add_argument(
        "--path",
        "-p",
        default=".",
        help="项目路径 (默认: 当前目录)"
    )
    
    parser.add_argument(
        "--llm",
        "-l",
        help="LLM 提供商 (格式: provider:model)"
    )


class SandboxConsole:
    """交互式沙盒控制台"""
    
    def __init__(self, agent_module=None, **kwargs):
        self.agent = agent_module
        self.context = None
        self.running = True
        self.step_count = 0
        self.snapshots: List[Dict] = []
    
    def print_banner(self):
        """打印欢迎横幅"""
        print("""
🧘 QitOS Interactive Sandbox
─────────────────────────────────────
输入 :help 查看可用命令
        """)
    
    def print_help(self):
        """打印帮助信息"""
        print("""
可用命令:
  (text)        作为用户输入发送给 Agent
  :step         仅执行一步（感知 -> 推理 -> 工具 -> 暂停）
  :ctx          打印当前 Context JSON
  :log          查看最近的 Mutation Log
  :undo         回滚到上一步
  :save <file>  保存当前现场快照
  :load <file>  加载现场快照
  :tools        列出可用工具
  :perf         显示性能统计
  :help         显示此帮助
  :quit / :exit 退出
        """)
    
    def cmd_ctx(self):
        """打印当前 Context"""
        if not self.context:
            print("❌  Context 未初始化")
            return
        
        ctx_json = self.context.to_json()
        print("\n📋 当前 Context:")
        print(ctx_json)
    
    def cmd_log(self):
        """查看 Mutation Log"""
        if not self.context:
            print("❌  Context 未初始化")
            return
        
        logs = self.context.mutation_log
        print(f"\n📝 Mutation Log (共 {len(logs)} 条):\n")
        
        for i, log in enumerate(logs[-10:]):  # 只显示最近10条
            print(f"  {i+1}. [Step {log.step}] {log.key}: {log.old_value} → {log.new_value}")
        
        if len(logs) > 10:
            print(f"\n  ... 还有 {len(logs) - 10} 条记录")
    
    def cmd_undo(self):
        """回滚到上一步"""
        if not self.context:
            print("❌  Context 未初始化")
            return
        
        if self.context.undo_last_mutation():
            print("✅ 已回滚一步")
        else:
            print("❌  无法回滚")
    
    def cmd_save(self, filename: str):
        """保存快照"""
        if not self.context:
            print("❌  Context 未初始化")
            return
        
        snapshot = {
            "context": json.loads(self.context.to_json()),
            "agent_class": self.agent.__class__.__name__ if self.agent else None,
            "step": self.context.current_step
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2)
        
        print(f"✅ 快照已保存到: {filename}")
        self.snapshots.append(snapshot)
    
    def cmd_load(self, filename: str):
        """加载快照"""
        from qitos.core.context import AgentContext
        
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.context = AgentContext.from_json(json.dumps(data["context"]))
            print(f"✅ 已加载快照 (Step {data.get('step', 0)})")
        
        except Exception as e:
            print(f"❌ 加载失败: {e}")
    
    def cmd_tools(self):
        """列出可用工具"""
        if not self.agent:
            print("❌  Agent 未初始化")
            return
        
        tools = self.agent.list_tools()
        print(f"\n🧰 可用工具 ({len(tools)} 个):\n")
        
        for name in tools:
            schema = self.agent.get_tool_schema(name)
            if schema:
                desc = schema.get("description", "")
                print(f"  • {name}: {desc}")
    
    def cmd_perf(self):
        """显示性能统计"""
        if not self.agent or not hasattr(self.agent, 'engine'):
            print("❌  引擎未初始化")
            return
        
        stats = self.agent.engine.get_performance_stats()
        print(f"\n📊 性能统计:")
        print(f"   总步数: {stats['total_steps']}")
        print(f"   总耗时: {stats['total_time']:.2f}s")
        print(f"   平均步耗时: {stats['avg_step_time']:.3f}s")
    
    def run_step(self, user_input: str) -> bool:
        """执行单步"""
        if not self.agent:
            print("❌  Agent 未初始化")
            return False
        
        # 如果是第一次运行，初始化 Context
        if not self.context:
            from qitos.core.context import AgentContext
            self.context = AgentContext(task=user_input)
            print(f"\n🚀 开始执行: {user_input[:50]}...")
        else:
            # 继续执行下一步
            self.context["task"] = user_input
        
        try:
            # 执行单步
            observations = self.agent.step(self.context)
            
            self.step_count += 1
            print(f"\n📍 Step {self.context.current_step - 1} → {self.context.current_step}")
            
            # 显示观察结果
            if observations:
                print(f"\n📊 观察结果 ({len(observations)} 个):")
                for i, obs in enumerate(observations):
                    obs_str = str(obs)
                    if len(obs_str) > 100:
                        obs_str = obs_str[:100] + "..."
                    print(f"   {i+1}. {obs_str}")
            else:
                print("\n✅  执行完成")
                if self.context.final_result:
                    print(f"\n🎉 最终答案:")
                    print(self.context.final_result)
                    return True  # 结束
        
        except Exception as e:
            print(f"❌  执行错误: {e}")
            import traceback
            if hasattr(self, 'verbose') and self.verbose:
                traceback.print_exc()
        
        return False
    
    def run(self):
        """运行交互式沙盒"""
        self.print_banner()
        
        while self.running:
            try:
                # 获取用户输入
                prompt = "\n👤 你: "
                user_input = input(prompt).strip()
                
                if not user_input:
                    continue
                
                # 处理命令
                if user_input.startswith(':'):
                    # 解析命令
                    parts = user_input.split(maxsplit=1)
                    cmd = parts[0].lower()
                    args = parts[1] if len(parts) > 1 else ""
                    
                    if cmd in [':quit', ':exit']:
                        print("👋 再见!")
                        self.running = False
                    
                    elif cmd == ':help':
                        self.print_help()
                    
                    elif cmd == ':step':
                        if not self.context:
                            print("❌  请先输入一个任务开始执行")
                        else:
                            # 继续执行下一步
                            self.run_step(self.context.task)
                    
                    elif cmd == ':ctx':
                        self.cmd_ctx()
                    
                    elif cmd == ':log':
                        self.cmd_log()
                    
                    elif cmd == ':undo':
                        self.cmd_undo()
                    
                    elif cmd == ':save':
                        if args:
                            self.cmd_save(args)
                        else:
                            print("❌  请指定文件名")
                            print("   用法: :save <file>")
                    
                    elif cmd == ':load':
                        if args:
                            self.cmd_load(args)
                        else:
                            print("❌  请指定文件名")
                            print("   用法: :load <file>")
                    
                    elif cmd == ':tools':
                        self.cmd_tools()
                    
                    elif cmd == ':perf':
                        self.cmd_perf()
                    
                    else:
                        print(f"❌  未知命令: {cmd}")
                        print("   输入 :help 查看可用命令")
                
                else:
                    # 作为用户输入执行
                    self.run_step(user_input)
            
            except KeyboardInterrupt:
                print("\n👋 用户中断")
                self.running = False
            
            except EOFError:
                print("\n👋 再见!")
                self.running = False


def run_play(args) -> int:
    """运行 play 命令"""
    import argparse
    
    try:
        console = SandboxConsole()
        console.run()
        return 0
    
    except Exception as e:
        print(f"❌ 错误: {e}")
        if hasattr(args, 'verbose') and args.verbose:
            import traceback
            traceback.print_exc()
        return 1
