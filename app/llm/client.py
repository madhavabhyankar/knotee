import json
from typing import Generator, Optional

import requests

DEFAULT_URL = "http://localhost:11434"
DEFAULT_MODEL = "llama3.2:3b"

_SUMMARY_PROMPT = """You are a meeting assistant. Given the transcript below, write a concise meeting summary in 3-5 bullet points covering the main topics discussed.

TRANSCRIPT:
{transcript}

SUMMARY:"""

_ACTIONS_PROMPT = """You are a meeting assistant. Given the transcript below, extract all action items — tasks someone agreed to do. Format as a numbered list. If there are none, say "No action items identified."

TRANSCRIPT:
{transcript}

ACTION ITEMS:"""


def is_ollama_available(base_url: str = DEFAULT_URL) -> bool:
    try:
        r = requests.get(f"{base_url}/api/tags", timeout=2)
        return r.status_code == 200
    except Exception:
        return False


def list_models(base_url: str = DEFAULT_URL) -> list[str]:
    try:
        r = requests.get(f"{base_url}/api/tags", timeout=5)
        data = r.json()
        return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []


def stream_completion(
    prompt: str,
    model: str = DEFAULT_MODEL,
    base_url: str = DEFAULT_URL,
) -> Generator[str, None, None]:
    payload = {"model": model, "prompt": prompt, "stream": True}
    with requests.post(
        f"{base_url}/api/generate",
        json=payload,
        stream=True,
        timeout=120,
    ) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if line:
                data = json.loads(line)
                yield data.get("response", "")
                if data.get("done"):
                    break


def generate_summary(
    transcript: str,
    model: str = DEFAULT_MODEL,
    base_url: str = DEFAULT_URL,
) -> Generator[str, None, None]:
    prompt = _SUMMARY_PROMPT.format(transcript=transcript)
    return stream_completion(prompt, model, base_url)


def generate_action_items(
    transcript: str,
    model: str = DEFAULT_MODEL,
    base_url: str = DEFAULT_URL,
) -> Generator[str, None, None]:
    prompt = _ACTIONS_PROMPT.format(transcript=transcript)
    return stream_completion(prompt, model, base_url)


class LLMWorker:
    """Thin wrapper used by UI to run LLM calls in a QThread."""
    pass
