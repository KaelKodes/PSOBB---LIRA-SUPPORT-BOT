"""OpenAI-compatible chat completion.

The token is sent only as a Bearer header. It is not written into the prompt,
the launch files, or the console.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request


def complete(cfg: dict, messages: list[dict]) -> str:
    llm = cfg["llm"]
    token = str(llm.get("token") or "").strip()
    model = str(llm.get("model") or "").strip()
    if not token or not model:
        raise RuntimeError("conversation is off")
    base = str(llm.get("base_url") or "").strip().rstrip("/")
    if not base:
        raise RuntimeError("conversation request failed")
    body = json.dumps(
        {
            "model": model,
            "temperature": 0.4,
            "max_tokens": 120,
            "messages": messages,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        base + "/chat/completions",
        data=body,
        method="POST",
    )
    request.add_header("Content-Type", "application/json")
    request.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        raise RuntimeError(f"conversation request failed ({err.code})") from None
    except OSError:
        raise RuntimeError("conversation request failed") from None
    try:
        return str(payload["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError):
        raise RuntimeError("conversation reply was empty") from None
