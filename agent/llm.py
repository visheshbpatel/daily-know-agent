"""Shared chat model: OpenAI or Google Gemini (configurable via env)."""

from __future__ import annotations

import os

from langchain_core.language_models.chat_models import BaseChatModel


def _is_real_key(value: str | None) -> bool:
    if not value or not str(value).strip():
        return False
    return str(value).strip().lower() not in ("your_key_here", "sk-your-actual-key-here")


def resolve_provider() -> str:
    """
    Which backend to use: 'google' or 'openai'.

    If LLM_PROVIDER is set to google or openai, that wins.
    Otherwise: prefer Google when GOOGLE_API_KEY is set, else OpenAI when OPENAI_API_KEY is set,
    else default to google (user adds a key from Google AI Studio).
    """
    explicit = (os.getenv("LLM_PROVIDER") or "").strip().lower()
    if explicit in ("google", "openai"):
        return explicit
    if _is_real_key(os.getenv("GOOGLE_API_KEY")):
        return "google"
    if _is_real_key(os.getenv("OPENAI_API_KEY")):
        return "openai"
    return "google"


def get_chat_llm(*, temperature: float) -> BaseChatModel:
    """Return a LangChain chat model for lesson/quiz chains."""
    provider = resolve_provider()
    if provider == "openai":
        from langchain_openai import ChatOpenAI

        model = os.getenv("OPENAI_MODEL", "gpt-4o")
        return ChatOpenAI(model=model, temperature=temperature)

    if provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI

        # Default to 1.5 Flash: 2.0 Flash often hits separate / zero free-tier quota per project.
        model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
        return ChatGoogleGenerativeAI(model=model, temperature=temperature)

    raise ValueError(f"Unknown LLM_PROVIDER: {provider!r}. Use 'google' or 'openai'.")


def provider_summary() -> str:
    """Short label for the sidebar (no secrets)."""
    p = resolve_provider()
    if p == "google":
        return f"Google Gemini ({os.getenv('GEMINI_MODEL', 'gemini-1.5-flash')})"
    return f"OpenAI ({os.getenv('OPENAI_MODEL', 'gpt-4o')})"
