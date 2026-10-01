import json
import os
import re

import requests

DEFAULT_BASE_URL = "https://llm.example.invalid/api"
DEFAULT_MODEL = "llm-model"
DEFAULT_TIMEOUT = 90
MAX_DOC_CHARS = 12000


def llm_config():
    return {
        "base_url": os.getenv("LLM_BASE_URL", DEFAULT_BASE_URL).rstrip("/"),
        "api_key": os.getenv("LLM_API_KEY") or os.getenv("PROVIDER_API_KEY"),
        "model": os.getenv("LLM_MODEL", DEFAULT_MODEL),
    }


def llm_available() -> bool:
    return bool(llm_config()["api_key"])


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return text.strip()


def parse_json_content(content: str):
    return json.loads(_strip_code_fences(content))


def llm_chat(system: str, user: str, json_mode: bool = False, temperature: float = 0.0):
    cfg = llm_config()
    if not cfg["api_key"]:
        raise RuntimeError("No LLM API key configured (set LLM_API_KEY or PROVIDER_API_KEY)")

    headers = {
        "Authorization": f"Bearer {cfg['api_key']}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": cfg["model"],
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
    content = response.json()["choices"][0]["message"]["content"]
    if json_mode:
        return parse_json_content(content)
    return content
