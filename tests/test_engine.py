"""
Test ExecutionEngine
"""

import pytest
from qitos.engine.execution_engine import (
    ExecutionEngine, 
    run_agent, 
    parse_tool_calls,
    ToolErrorHandler,
    ActionParser,
    DefaultActionParser,
    ReActActionParser
)
from qitos.core.agent import AgentModule
from qitos.core.context import AgentContext
from qitos.core.skill import ToolRegistry, skill


class TestParseToolCalls:
    """测试工具调用解析"""
    
    def test_final_answer(self):
        """测试最终答案检测"""
        text = "Final Answer: 这就是答案"
        
        result = parse_tool_calls(text, [])
        
        assert result["is_final"] is True
        assert result["content"] == "这就是答案"
    
    def test_tool_call_simple(self):
        """测试简单工具调用"""
        text = 'Action: search(query="python")'
        
        result = parse_tool_calls(text, ["search"])
        
        assert result["is_final"] is False
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["tool"] == "search"
    
    def test_tool_call_with_number(self):
        """测试带编号的工具调用"""
        text = '''Action 1: search
{"query": "python"}'''
        
        result = parse_tool_calls(text, ["search"])
        
        assert result["is_final"] is False
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["tool"] == "search"
    
    def test_unknown_tool(self):
        """测试未知工具调用"""
        text = 'Action: unknown_tool(arg=1)'
        
        result = parse_tool_calls(text, ["search"])
        
        assert result["is_final"] is True
    
    def test_no_action(self):
        """测试无工具调用"""
        text = "I think we should..."
        
        result = parse_tool_calls(text, ["search"])
        
        assert result["is_final"] is True


class TestActionParser:
    """测试 ActionParser 类"""
    
    def test_action_parser_init(self):
        """测试解析器初始化"""
        parser = ActionParser()
        assert parser is not None
    
    def test_default_action_parser(self):
        """测试默认解析器"""
        parser = DefaultActionParser()
        assert parser is not None
    
    def test_react_action_parser(self):
        """测试 ReAct 解析器"""
        parser = ReActActionParser()
        assert parser is not None
    
    def test_parser_returns_list(self):
        """测试解析器返回列表格式"""
        parser = DefaultActionParser()
        actions = parser.parse('Action: search(query="test")', ["search"])
        
        assert isinstance(actions, list)
        assert len(actions) > 0
        assert "name" in actions[0]
        assert "args" in actions[0]
        assert "error" in actions[0]


class TestExecutionEngine:
    """测试 ExecutionEngine"""
    
    def test_engine_init(self):
        """测试引擎初始化"""
        class MockAgent:
            toolkit = ToolRegistry()
            llm = None
            def update_context(self, context, observations):
                pass
        
        agent = MockAgent()
        engine = ExecutionEngine(agent=agent)
        
        assert engine is not None
        assert engine.agent == agent
        assert engine.parser is not None
    
    def test_engine_with_custom_parser(self):
        """测试引擎自定义解析器"""
        class MockAgent:
            toolkit = ToolRegistry()
            llm = None
            def update_context(self, context, observations):
                pass
        
        agent = MockAgent()
        parser = DefaultActionParser()
        engine = ExecutionEngine(agent=agent, parser=parser)
        
        assert engine.parser == parser
    
    def test_engine_with_stopping_criteria(self):
        """测试引擎自定义结束条件"""
        class MockAgent:
            toolkit = ToolRegistry()
            llm = None
            def update_context(self, context, observations):
                pass
        
        agent = MockAgent()
        
        def custom_stop(context, response):
            return "stop" in str(response).lower()
        
        engine = ExecutionEngine(
            agent=agent,
            stopping_criteria=custom_stop
        )
        
        assert engine.stopping_criteria == custom_stop
    
    def test_is_finished_max_steps(self):
        """测试步数限制结束"""
        class MockAgent:
            toolkit = ToolRegistry()
            llm = None
            def update_context(self, context, observations):
                pass
        
        agent = MockAgent()
        engine = ExecutionEngine(agent=agent)
        
        context = AgentContext(task="test", max_steps=2)
        context["current_step"] = 2
        
        assert engine.is_finished(context, "response") is True
        assert context.metadata["stop_reason"] == "max_steps_reached"
    
    def test_is_finished_custom_criteria(self):
        """测试自定义结束条件"""
        class MockAgent:
            toolkit = ToolRegistry()
            llm = None
            def update_context(self, context, observations):
                pass
        
        agent = MockAgent()
        
        def stop_on_keyword(context, response):
            return "success" in str(response).lower()
        
        engine = ExecutionEngine(
            agent=agent,
            stopping_criteria=stop_on_keyword
        )
        
        context = AgentContext(task="test")
        context["current_step"] = 0
        
        assert engine.is_finished(context, "This is a success response") is True
        assert context.metadata["stop_reason"] == "custom_criteria"
    
    def test_is_finished_final_answer(self):
        """测试最终答案结束"""
        class MockAgent:
            toolkit = ToolRegistry()
            llm = None
            def update_context(self, context, observations):
                pass
        
        agent = MockAgent()
        engine = ExecutionEngine(agent=agent)
        
        context = AgentContext(task="test")
        
        assert engine.is_finished(context, "Final Answer: done") is True
        assert context.metadata["stop_reason"] == "final_answer"
    
    def test_is_finished_not_finished(self):
        """测试未结束"""
        class MockAgent:
            toolkit = ToolRegistry()
            llm = None
            def update_context(self, context, observations):
                pass
        
        agent = MockAgent()
        engine = ExecutionEngine(agent=agent)
        
        context = AgentContext(task="test", max_steps=10)
        context["current_step"] = 0
        
        assert engine.is_finished(context, "Please call a tool") is False


class TestMultiToolExecution:
    """测试多工具并行执行"""
    
    def test_multiple_actions_parsing(self):
        """测试多 Action 解析"""
        parser = DefaultActionParser()
        
        text = '''Action: search(query="python")
Action: download(url="http://example.com")'''
        
        actions = parser.parse(text, ["search", "download"])
        
        assert len(actions) == 2
        assert actions[0]["name"] == "search"
        assert actions[1]["name"] == "download"
    
    def test_error_feedback(self):
        """测试错误反馈"""
        parser = DefaultActionParser()
        
        text = 'Action: unknown_tool(args)'
        
        actions = parser.parse(text, ["search"])
        
        assert len(actions) == 1
        assert actions[0]["name"] is None
        assert "Unknown tool" in actions[0]["error"]
    
    def test_valid_json_action(self):
        """测试有效 JSON Action"""
        parser = DefaultActionParser()
        
        text = "Action: {\"name\": \"search\", \"args\": {\"query\": \"test\"}}"
        
        actions = parser.parse(text, ["search"])
        
        found = False
        for action in actions:
            if action.get("error") is None and action.get("name") == "search":
                found = True
                break
        
        assert found, f"No valid search action found in: {actions}"
    
    def test_final_answer_with_prefix(self):
        """测试带前缀的最终答案"""
        parser = DefaultActionParser()
        
        text = "结论: 任务完成"
        
        actions = parser.parse(text, [])
        
        assert len(actions) == 1
        assert actions[0]["name"] == "FINAL_ANSWER"
        assert "任务完成" in str(actions[0]["args"])
