"""
QitOS Models Module

统一的大模型调用接口。

提供多种模型支持：
- OpenAI (GPT-4, GPT-3.5)
- OpenAI 兼容 (Azure, 通义千问, 智谱 AI 等)
- 本地模型 (Ollama, LM Studio, vLLM)

Usage:
    # OpenAI
    from qitos.models import OpenAIModel
    llm = OpenAIModel(model="gpt-4")
    
    # Ollama
    from qitos.models import OllamaModel
    llm = OllamaModel(model="llama3")
    
    # 从环境变量自动选择
    from qitos.models import ModelFactory
    llm = ModelFactory.from_env()
"""

from .base import Model, AsyncModel, ModelFactory
from .openai import OpenAIModel, OpenAICompatibleModel, AzureOpenAIModel
from .local import (
    OllamaModel,
    OllamaGenerateModel,
    LMStudioModel,
    VLLMModel
)

__all__ = [
    # 基类
    "Model",
    "AsyncModel",
    "ModelFactory",
    
    # OpenAI
    "OpenAIModel",
    "OpenAICompatibleModel",
    "AzureOpenAIModel",
    
    # 本地模型
    "OllamaModel",
    "OllamaGenerateModel",
    "LMStudioModel",
    "VLLMModel",
]
