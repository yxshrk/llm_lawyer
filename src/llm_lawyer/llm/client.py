import logging
from dataclasses import dataclass
from functools import lru_cache

from openai import (
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    RateLimitError,
)

from llm_lawyer.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class ChatResult:
    text: str
    provider: str
    model: str
    prompt_tokens: int
    cached_prompt_tokens: int
    completion_tokens: int


# All three providers speak the OpenAI Chat Completions protocol.
# Gemini + Groq expose OpenAI-compatible endpoints, so one SDK handles all three.
PROVIDER_BASE_URLS: dict[str, str | None] = {
    "openai": None,  # default api.openai.com
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "groq": "https://api.groq.com/openai/v1",
}


def _provider_key(provider: str) -> str:
    s = get_settings()
    return {
        "openai": s.openai_api_key,
        "gemini": s.gemini_api_key,
        "groq": s.groq_api_key,
    }.get(provider, "")


def _provider_model(provider: str) -> str:
    s = get_settings()
    return {
        "openai": s.openai_model,
        "gemini": s.gemini_model,
        "groq": s.groq_model,
    }.get(provider, "")


@lru_cache
def _client_for(provider: str) -> AsyncOpenAI:
    base_url = PROVIDER_BASE_URLS[provider]
    return AsyncOpenAI(api_key=_provider_key(provider), base_url=base_url)


FALLBACK_EXCEPTIONS = (
    RateLimitError,
    AuthenticationError,
    APIConnectionError,
    APITimeoutError,
    BadRequestError,
    InternalServerError,
    APIStatusError,
    APIError,
)


async def chat_completion(
    messages: list[dict],
    *,
    task: str = "narrative",
    json_mode: bool = False,
) -> ChatResult:
    """Try providers in priority order, falling back on any SDK-level failure.

    Args:
        task: "structured" (low temp, for JSON outputs like redaction, SW) or
            "narrative" (higher temp, for memo/chat).
        json_mode: when True, asks the provider for strict JSON output
            (OpenAI + Gemini compat support `response_format={"type": "json_object"}`;
            Groq ignores it gracefully).
    """
    s = get_settings()
    providers = [
        p for p in s.llm_providers
        if p in PROVIDER_BASE_URLS and _provider_key(p)
    ]
    if not providers:
        raise RuntimeError(
            "No LLM provider configured — set OPENAI_API_KEY, GEMINI_API_KEY, or GROQ_API_KEY"
        )

    temperature = s.llm_temp_structured if task == "structured" else s.llm_temp_narrative

    last_err: Exception | None = None
    for provider in providers:
        kwargs: dict = {
            "model": _provider_model(provider),
            "messages": messages,
            "max_completion_tokens": s.llm_max_output_tokens,
            "temperature": temperature,
        }
        if json_mode and provider in ("openai", "gemini"):
            kwargs["response_format"] = {"type": "json_object"}
        try:
            resp = await _client_for(provider).chat.completions.create(**kwargs)
        except FALLBACK_EXCEPTIONS as e:
            logger.warning(
                "LLM provider %s failed (%s: %s); trying next",
                provider,
                type(e).__name__,
                str(e)[:200],
            )
            last_err = e
            continue
        except Exception as e:
            # Catch-all so we never 500 the request if a new SDK error type
            # appears — log loudly but still try the next provider.
            logger.warning(
                "LLM provider %s raised unexpected %s (%s); trying next",
                provider,
                type(e).__name__,
                str(e)[:200],
            )
            last_err = e
            continue

        if not resp.choices:
            logger.warning("LLM provider %s returned no choices; trying next", provider)
            last_err = RuntimeError(f"{provider}: empty choices")
            continue

        choice = resp.choices[0]
        text = (choice.message.content or "").strip()
        if not text:
            logger.warning("LLM provider %s returned empty content; trying next", provider)
            last_err = RuntimeError(f"{provider}: empty content")
            continue

        usage = resp.usage
        cached = 0
        if usage and getattr(usage, "prompt_tokens_details", None) is not None:
            cached = getattr(usage.prompt_tokens_details, "cached_tokens", 0) or 0
        return ChatResult(
            text=text,
            provider=provider,
            model=resp.model,
            prompt_tokens=usage.prompt_tokens if usage else 0,
            cached_prompt_tokens=cached,
            completion_tokens=usage.completion_tokens if usage else 0,
        )

    assert last_err is not None
    raise last_err
