from app.llm.models import LLMProviderConfig, ProviderKind
from app.llm.providers.base import LLMProvider

DEFAULT_BASE_URLS: dict[ProviderKind, str] = {
    ProviderKind.OPENAI: "https://api.openai.com/v1",
    ProviderKind.ANTHROPIC: "https://api.anthropic.com",
    ProviderKind.GEMINI: "https://generativelanguage.googleapis.com/v1beta/openai",
    ProviderKind.DEEPSEEK: "https://api.deepseek.com/v1",
    ProviderKind.QWEN: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    ProviderKind.OLLAMA: "http://host.docker.internal:11434/v1",
}


def build_provider(config: LLMProviderConfig) -> LLMProvider:
    from app.llm.providers.anthropic import AnthropicProvider
    from app.llm.providers.openai_compat import OpenAICompatProvider

    if config.kind is ProviderKind.ANTHROPIC:
        return AnthropicProvider(config)
    return OpenAICompatProvider(config)
