"""匹配引擎（从 jd-fit 复用，零依赖）。对外暴露核心函数。"""

from .extract import extract_requirements, extract_title
from .family_llm import FamilyVerdict, detect_families, detect_family_llm
from .llm import LLM, LLMError
from .match import counterfactual, gaps, match, match_by_rules, score
from .render import render
from .schema import Assessment, MatchResult, Requirement, detect_domains

__all__ = [
    "LLM", "LLMError", "Assessment", "MatchResult", "Requirement",
    "extract_requirements", "extract_title", "match", "match_by_rules",
    "score", "gaps", "counterfactual", "render", "detect_domains",
    "detect_families", "detect_family_llm", "FamilyVerdict",
]
