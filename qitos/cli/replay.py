"""CLI command: qitos replay - Replay execution trace"""

import os
import json
from typing import Dict, Optional


def add_replay_parser(subparsers):
    """添加 replay 子命令到 parser"""
    parser = subparsers.add_parser(
        "replay",
        help="重放执行轨迹",
        description="从保存的 trace 文件重现 Agent 的执行过程，用于调试。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s trace.json                    # 重放 trace.json
  %(prog)s trace.json --step 2           # 从第2步开始
  %(prog)s trace.json --diff              # 显示每步差异
        """
    )
    
    parser.add_argument(
        "trace_file",
        help="trace 文件路径"
    )
    
    parser.add_argument(
        "--step",
        "-s",
        type=int,
        default=0,
        help="从指定步骤开始 (默认: 0)"
    )
    
    parser.add_argument(
        "--diff",
        "-d",
        action="store_true",
        help="显示每步的状态差异"
    )
    
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="详细输出"


def run_replay(args) -> int:
    """运行 replay 命令"""
    import argparse
    
    trace_file = args.trace_file
    
    # 检查文件是否存在
    if not os.path.exists(trace_file):
        print(f"❌ 错误: 文件不存在: {trace_file}")
        return 1
    
    # 加载 trace
    try:
        with open(trace_file, 'r', encoding='utf-8') as f:
            trace = json.load(f)
    
    except json.JSONDecodeError as e:
        print(f"❌ 错误: 无效的 JSON 文件: {e}")
        return 1
    
    except Exception as e:
        print(f"❌ 错误: 读取文件失败: {e}")
        return 1
    
    # 显示 trace 信息
    print("🧘 QitOS Trace Replay")
    print("─" * 40)
    
    # 解析 trace 头部信息
    task = trace.get('task', 'Unknown')
    max_steps = trace.get('max_steps', 'Unknown')
    steps = trace.get('_observation_history', [])
    
    print(f"📋 任务: {task[:60]}..." if len(task) > 60 else f"📋 任务: {task}")
    print(f"📊 步数: {len(steps)} / {max_steps}")
    print(f"📁 文件: {os.path.abspath(trace_file)}")
    print()
    
    # 检查是否有最终结果
    if trace.get('_final_result'):
        print("🎉 最终答案:")
        print(trace['_final_result'])
        print()
    
    # 重放执行过程
    start_step = args.step
    end_step = len(steps)
    
    if start_step >= end_step:
        print(f"❌ 错误: 起始步骤 {start_step} 大于总步数 {end_step}")
        return 1
    
    print(f"🔄 从 Step {start_step} 开始重放...\n")
    
    for i in range(start_step, end_step):
        step_data = steps[i]
        step = step_data.get('step', i)
        observations = step_data.get('observations', [])
        raw_output = step_data.get('raw_output', '')
        
        print(f"📍 Step {step}")
        print("─" * 20)
        
        # 显示 LLM 输出
        if raw_output:
            output_preview = raw_output[:100] + "..." if len(raw_output) > 100 else raw_output
            print(f"🤖 LLM: {output_preview}")
        
        # 显示观察结果
        if observations:
            print(f"\n📊 观察结果 ({len(observations)} 个):")
            for j, obs in enumerate(observations):
                obs_str = str(obs)
                if len(obs_str) > 80:
                    obs_str = obs_str[:80] + "..."
                print(f"   {j+1}. {obs_str}")
        
        # 显示差异
        if args.diff and i > 0:
            prev_step = steps[i - 1]
            ctx_diff = _compute_diff(prev_step, step_data)
            if ctx_diff:
                print(f"\n📝 状态变更:")
                for key, (old, new) in ctx_diff.items():
                    print(f"   {key}: {old} → {new}")
        
        print()
    
    # 显示 mutation log
    mutation_log = trace.get('_mutation_log', [])
    if mutation_log:
        print(f"📝 Mutation Log (共 {len(mutation_log)} 条):")
        for log in mutation_log[-5:]:  # 只显示最近5条
            print(f"   [Step {log.get('step', '?')}] {log.get('key', '?')}")
        
        if len(mutation_log) > 5:
            print(f"   ... 还有 {len(mutation_log) - 5} 条")
        print()
    
    # 性能统计
    if '_performance' in trace:
        perf = trace['_performance']
        print(f"📊 性能统计:")
        print(f"   总耗时: {perf.get('total_time', 'N/A')}")
        print()
    
    # 错误检测
    errors = _detect_errors(steps)
    if errors:
        print("⚠️  检测到以下问题:")
        for error in errors:
            print(f"   • {error}")
        print()
    
    return 0


def _compute_diff(prev: Dict, curr: Dict) -> Dict[str, tuple]:
    """计算两个步骤之间的差异"""
    diff = {}
    
    # 比较 observations
    prev_obs = prev.get('observations', [])
    curr_obs = curr.get('observations', [])
    
    if prev_obs != curr_obs:
        diff['observations'] = (len(prev_obs), len(curr_obs))
    
    # 比较 raw_output
    prev_raw = prev.get('raw_output', '')
    curr_raw = curr.get('raw_output', '')
    
    if prev_raw != curr_raw:
        diff['raw_output'] = ('changed', 'changed')
    
    return diff


def _detect_errors(steps: list) -> list:
    """检测执行过程中的错误"""
    errors = []
    
    for i, step_data in enumerate(steps):
        observations = step_data.get('observations', [])
        
        for obs in observations:
            obs_str = str(obs)
            
            # 检测错误标志
            if 'error' in obs_str.lower() or 'Error' in obs_str:
                errors.append(f"Step {i}: {obs_str[:100]}")
            
            # 检测异常
            if 'exception' in obs_str.lower() or 'Exception' in obs_str:
                errors.append(f"Step {i}: 检测到异常")
    
    return errors


def _print_timeline(trace: Dict):
    """打印时间线视图"""
    steps = trace.get('_observation_history', [])
    
    print("📅 Timeline View")
    print("─" * 40)
    
    for i, step_data in enumerate(steps):
        step = step_data.get('step', i)
        timestamp = step_data.get('timestamp', 'Unknown')
        tool_calls = step_data.get('tool_calls', [])
        
        # 格式化时间戳
        if timestamp != 'Unknown':
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                time_str = dt.strftime('%H:%M:%S')
            except Exception:
                time_str = timestamp[:19] if len(timestamp) > 19 else timestamp
        else:
            time_str = '??:??:??'
        
        # 显示工具调用
        tools = ", ".join([tc.get('tool', '?') for tc in tool_calls]) if tool_calls else 'no tools'
        
        print(f"  {i:2d}. [{time_str}] Step {step}: {tools}")
    
    print()


def _print_diff_view(trace: Dict, step: int):
    """打印 Diff View"""
    steps = trace.get('_observation_history', [])
    
    if step <= 0 or step >= len(steps):
        print(f"❌ 无效步骤: {step}")
        return
    
    prev_step = steps[step - 1]
    curr_step = steps[step]
    
    print(f"📝 Diff View - Step {step - 1} → {step}")
    print("─" * 40)
    
    # 比较字段
    fields = ['observations', 'raw_output', 'messages']
    
    for field in fields:
        prev_val = prev_step.get(field, None)
        curr_val = curr_step.get(field, None)
        
        if prev_val != curr_val:
            print(f"\n  {field}:")
            print(f"    - {str(prev_val)[:100]}{'...' if len(str(prev_val)) > 100 else ''}")
            print(f"    + {str(curr_val)[:100]}{'...' if len(str(curr_val)) > 100 else ''}")
    
    print()
