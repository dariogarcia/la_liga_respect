import json
import os
import re

import requests

DEFAULT_BASE_URL = "https://llm.example.invalid/api"
DEFAULT_MODEL = "llm-model"
DEFAULT_TIMEOUT = 90
MAX_DOC_CHARS = 12000

# B2: hard cap on LLM calls per run; 0 disables the cap.
DEFAULT_MAX_LLM_CALLS_PER_RUN = 300


class LLMBudgetExceeded(RuntimeError):
    """Raised when the run has exhausted its LLM call budget."""


def llm_config():
    return {
        "base_url": os.getenv("LLM_BASE_URL", DEFAULT_BASE_URL).rstrip("/"),
        "api_key": os.getenv("LLM_API_KEY") or os.getenv("PROVIDER_API_KEY"),
        "model": os.getenv("LLM_MODEL", DEFAULT_MODEL),
    }


def llm_available() -> bool:
    return bool(llm_config()["api_key"])


def _max_llm_calls() -> int:
    raw = os.environ.get("MAX_LLM_CALLS_PER_RUN")
    if raw is None:
        return DEFAULT_MAX_LLM_CALLS_PER_RUN
    try:
        return max(0, int(raw))
    except ValueError:
        return DEFAULT_MAX_LLM_CALLS_PER_RUN


# B2: usage counters for the run report.
_LLM_USAGE = {
    "calls": 0,
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "by_purpose": {},
}


def llm_usage() -> dict:
    """A copy of this run's LLM usage counters."""
    usage = dict(_LLM_USAGE)
    usage["by_purpose"] = dict(_LLM_USAGE["by_purpose"])
    return usage


def reset_llm_usage() -> None:
    _LLM_USAGE["calls"] = 0
    _LLM_USAGE["prompt_tokens"] = 0
    _LLM_USAGE["completion_tokens"] = 0
    _LLM_USAGE["by_purpose"] = {}


def _record_usage(purpose: str, response_json: dict) -> None:
    _LLM_USAGE["calls"] += 1
    _LLM_USAGE["by_purpose"][purpose] = _LLM_USAGE["by_purpose"].get(purpose, 0) + 1
    usage = response_json.get("usage") or {}
    _LLM_USAGE["prompt_tokens"] += int(usage.get("prompt_tokens") or 0)
    _LLM_USAGE["completion_tokens"] += int(usage.get("completion_tokens") or 0)


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return text.strip()


def parse_json_content(content: str):
    return json.loads(_strip_code_fences(content))


def llm_chat(
    system: str,
    user: str,
    json_mode: bool = False,
    temperature: float = 0.0,
    purpose: str = "default",
    model: str = None,
):
    """Calls the configured chat-completions endpoint.

    - `purpose` tags the call in the run's usage counters (B2).
    - `model` overrides the configured model for this call (B4: a
      cheaper extraction model, via LLM_EXTRACT_MODEL).
    - Raises LLMBudgetExceeded once MAX_LLM_CALLS_PER_RUN is reached;
      callers are expected to degrade gracefully.
    """
    cfg = llm_config()
    if not cfg["api_key"]:
        raise RuntimeError("No LLM API key configured (set LLM_API_KEY or PROVIDER_API_KEY)")

    limit = _max_llm_calls()
    if limit and _LLM_USAGE["calls"] >= limit:
        raise LLMBudgetExceeded(
            f"LLM call budget exhausted ({_LLM_USAGE['calls']}/{limit} calls). "
            f"Raise MAX_LLM_CALLS_PER_RUN to allow more."
        )

    headers = {
        "Authorization": f"Bearer {cfg['api_key']}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model or cfg["model"],
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    response = requests.post(
        f"{cfg['base_url']}/chat/completions",
        headers=headers,
        json=payload,
        timeout=DEFAULT_TIMEOUT,
    )
    if response.status_code == 400 and json_mode:
        payload.pop("response_format", None)
        response = requests.post(
            f"{cfg['base_url']}/chat/completions",
            headers=headers,
            json=payload,
            timeout=DEFAULT_TIMEOUT,
        )
    response.raise_for_status()
    body = response.json()
    _record_usage(purpose, body)
    content = body["choices"][0]["message"]["content"]
    if json_mode:
        return parse_json_content(content)
    return content
