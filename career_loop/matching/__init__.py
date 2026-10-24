"""匹配引擎（从 jd-fit 复用，零依赖）。对外暴露核心函数。"""

from .extract import extract_requirements, extract_title
from .llm import LLM, LLMError
from .match import gaps, match, match_by_rules, score
from .render import render
from .schema import Assessment, MatchResult, Requirement

__all__ = [
    "LLM", "LLMError", "Assessment", "MatchResult", "Requirement",
    "extract_requirements", "extract_title", "match", "match_by_rules",
    "score", "gaps", "render",
]
