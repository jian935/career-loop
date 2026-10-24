"""Lightweight OpenAI-compatible LLM client. Zero third-party dependencies."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

DEFAULT_BASE = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-chat"


class LLMError(RuntimeError):
    pass


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def parse_json_loose(text: str) -> dict:
    """Parse JSON out of an LLM reply that may contain prose or fences."""
    cleaned = _strip_code_fence(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end > start:
        return json.loads(cleaned[start : end + 1])
    raise LLMError(f"模型没有返回合法 JSON：{cleaned[:200]}")


class LLM:
    def __init__(self, base_url=None, api_key=None, model=None, timeout=90):
        self.base_url = (
            base_url or os.getenv("JD_FIT_BASE_URL") or DEFAULT_BASE
        ).rstrip("/")
        self.api_key = api_key or os.getenv("JD_FIT_API_KEY") or os.getenv("OPENAI_API_KEY")
        self.model = model or os.getenv("JD_FIT_MODEL") or DEFAULT_MODEL
        self.timeout = timeout

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def chat(self, system: str, user: str, temperature: float = 0.2) -> str:
        if not self.available:
            raise LLMError("未配置 API Key")
        payload = {
            "model": self.model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        req = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "ignore")[:300]
            raise LLMError(f"HTTP {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise LLMError(f"网络错误: {exc.reason}") from exc
        return data["choices"][0]["message"]["content"]

    def json(self, system: str, user: str) -> dict:
        return parse_json_loose(self.chat(system, user))
