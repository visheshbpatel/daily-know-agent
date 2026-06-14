"""LangChain chain for structured lesson generation."""

from pathlib import Path

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from pydantic import BaseModel, Field

from agent.llm import get_chat_llm

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "lesson_prompt.txt"


class Lesson(BaseModel):
    what_it_is: str
    why_it_matters: str
    key_facts: list[str]
    analogy: str
    real_world_example: str = ""
    code_snippet: dict[str, str] = Field(default_factory=dict)


def _load_prompt_template() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _normalize_lesson(d: dict) -> dict:
    facts = list(d.get("key_facts") or [])
    while len(facts) < 3:
        facts.append("(Additional detail not provided.)")
    d["key_facts"] = facts[:3]
    d["real_world_example"] = str(d.get("real_world_example") or "").strip()
    snippet = d.get("code_snippet") or {}
    if not isinstance(snippet, dict):
        snippet = {}
    d["code_snippet"] = {
        "language": str(snippet.get("language") or "").strip(),
        "snippet": str(snippet.get("snippet") or "").strip(),
        "explanation": str(snippet.get("explanation") or "").strip(),
    }
    return d


def generate_lesson(topic: str) -> dict:
    """Generate a structured lesson dict for the given topic."""
    parser = JsonOutputParser(pydantic_object=Lesson)
    prompt = PromptTemplate(
        template=_load_prompt_template() + "\n\n{format_instructions}",
        input_variables=["topic"],
        partial_variables={"format_instructions": parser.get_format_instructions()},
    )
    llm = get_chat_llm(temperature=0.7)
    chain = prompt | llm | parser
    result = chain.invoke({"topic": topic})
    if isinstance(result, Lesson):
        data = result.model_dump()
    else:
        data = dict(result)
    return _normalize_lesson(data)
