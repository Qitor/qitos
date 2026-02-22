# `qitos.models.openai`

- Module Group: `qitos.models`
- Source: [qitos/models/openai.py](https://github.com/Qitor/qitos/blob/main/qitos/models/openai.py)

## Quick Jump

- [Classes](#classes)
- [Functions](#functions)
- [Class: `AzureOpenAIModel`](#class-azureopenaimodel)
- [Class: `OpenAICompatibleModel`](#class-openaicompatiblemodel)
- [Class: `OpenAIModel`](#class-openaimodel)

## Classes

<a id="class-azureopenaimodel"></a>
???+ note "Class: `AzureOpenAIModel(self, deployment: Optional[str] = None, api_key: Optional[str] = None, endpoint: Optional[str] = None, api_version: str = '2024-02-15-preview', system_prompt: Optional[str] = None, temperature: float = 0.7, max_tokens: int = 2048, timeout: int = 60)`"
    Azure OpenAI model implementation

<a id="class-openaicompatiblemodel"></a>
???+ note "Class: `OpenAICompatibleModel(self, model: str = 'default', api_key: Optional[str] = None, base_url: Optional[str] = None, system_prompt: Optional[str] = None, temperature: float = 0.7, max_tokens: int = 2048, timeout: int = 60)`"
    OpenAI compatible interface model

<a id="class-openaimodel"></a>
???+ note "Class: `OpenAIModel(self, model: str = 'gpt-4', api_key: Optional[str] = None, base_url: Optional[str] = None, system_prompt: Optional[str] = None, temperature: float = 0.7, max_tokens: int = 2048, timeout: int = 60)`"
    OpenAI model calling implementation

## Functions

- _None_

## Source Index

- [qitos/models/openai.py](https://github.com/Qitor/qitos/blob/main/qitos/models/openai.py)