"""LangChain chain for quiz generation and answer evaluation."""

import json
import re
from pathlib import Path

from langchain_core.prompts import PromptTemplate
from pydantic import BaseModel, Field

from agent.llm import get_chat_llm

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "quiz_prompt.txt"


class QuizQuestion(BaseModel):
    question: str
    options: list[str] = Field(..., min_length=4, max_length=4)
    answer: str


def _load_prompt_template() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _message_content_to_str(content: object) -> str:
    """OpenAI returns str; Gemini often returns a list of text parts."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
                else:
                    parts.append(str(block))
            else:
                parts.append(str(block))
        return "".join(parts)
    return str(content)


def _extract_json_array(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```\s*$", "", text)
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("Model did not return a JSON array.")
    return text[start : end + 1]


def generate_quiz(lesson: dict) -> list[dict]:
    """Generate three multiple-choice questions from a lesson dict."""
    lesson_text = json.dumps(lesson, ensure_ascii=False, indent=2)
    prompt = PromptTemplate.from_template(_load_prompt_template())
    llm = get_chat_llm(temperature=0.5)
    chain = prompt | llm
    raw = chain.invoke({"lesson_text": lesson_text})
    content = _message_content_to_str(raw.content if hasattr(raw, "content") else raw)
    snippet = _extract_json_array(content)
    data = json.loads(snippet)
    if not isinstance(data, list) or len(data) != 3:
        raise ValueError("Expected exactly 3 quiz questions.")
    return [QuizQuestion.model_validate(item).model_dump() for item in data]


def _normalize_letter(value: str) -> str:
    if not value or not str(value).strip():
        return ""
    s = str(value).strip().upper()
    if s and s[0] in "ABCD":
        return s[0]
    return ""


def evaluate_answer(question: dict, user_answer: str, correct_answer: str) -> bool:
    """Return True if the user's choice matches the correct option letter (A–D)."""
    _ = question  # reserved for future scoring tweaks
    return _normalize_letter(user_answer) == _normalize_letter(correct_answer)
