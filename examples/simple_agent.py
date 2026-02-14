from typing import List, Any, Optional
from qitos import AgentModule, AgentContext, ToolRegistry
from qitos.models import OpenAICompatibleModel
from qitos.render import RichConsoleHook

# 1. 定义工具函数（严格遵循 QitOS 的 Docstring 规范）
def add(a: int, b: int) -> int:
    """
    执行加法运算。
    
    :param a: 第一个整数
    :param b: 第二个整数
    
    Returns the sum of two numbers
    """
    return a + b

def multiply(a: int, b: int) -> int:
    """
    执行乘法运算。
    
    :param a: 乘数
    :param b: 被乘数
    
    Returns the product of two numbers
    """
    return a * b

# 2. 继承 AgentModule 实现 ReAct 逻辑
class CalculatorExpert(AgentModule):
    # 使用 {{tool_schema}} 占位符，Engine 会自动注入 ToolRegistry 里的工具描述
    system_prompt = """你是一位严谨的数学专家，擅长通过分步推理和工具调用来解决复杂问题。请严格采用 ReAct（Reasoning + Acting）范式进行思考与操作。

可用工具如下：
{{tool_schema}}

给你的信息格式如下
Task: [Goal]
Observation: [工具返回的结果将在此处自动填充]

当需要调用工具，输出如下格式：

Thought: 分析当前问题，明确下一步需要获取的信息或执行的操作。
Action: 工具名称(参数名=参数值) 

若无需工具，则直接输出：
Thought: ...
Final Answer: 基于所有推理和观察结果，给出清晰、准确、完整的最终答案。

注意事项：
- 每次只执行一个 Action。
- 不要编造工具不存在的功能或参数。
- 如果已有足够信息解答问题，请勿继续调用工具，直接输出 Final Answer。
    """

    def gather(self, context: AgentContext) -> str:
        """
        gather 只需要返回当前的增量任务。
        历史对话（Memory）由 Engine 自动编排，不需要在这里手动拼接。
        """
        return f"""当前任务：{context.task}

Observation: {context.last_obs}"""

# 3. 运行示例
if __name__ == "__main__":
    # 注册工具（ToolRegistry 会自动解析上面的 docstring）
    registry = ToolRegistry()
    registry.register(add)
    registry.register(multiply)

    llm = OpenAICompatibleModel(
        model="Qwen/Qwen3-8B",
        base_url="https://api.siliconflow.cn/v1",
        api_key="sk-nbxooqwpyyvzfexesvwqgogfogvicxmpyscqgihtsuvyyimr"
    )

    # 初始化 Agent
    agent = CalculatorExpert(toolkit=registry, llm=llm)
    hook = RichConsoleHook()
    
    # 执行任务
    # run 会启动 ExecutionEngine，自动处理 get_system_prompt 和占位符替换
    result = agent.run("请帮我算一下 112390 * 23 是多少", max_steps=8, hooks=[hook])
