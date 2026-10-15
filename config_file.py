"""Local config for a Lira checkout.

config.json stays on the machine that runs her. The example file ships with
the account, password, and conversation token empty.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"
EXAMPLE_PATH = ROOT / "config.example.json"


def _ascii(value, label: str, limit: int, *, allow_empty: bool = True) -> str:
    text = str(value or "").strip()
    if not text and allow_empty:
        return ""
    if not text:
        raise ValueError(f"{label} is empty")
    if len(text) > limit or any(ord(ch) < 32 or ord(ch) > 126 for ch in text):
        raise ValueError(f"{label} must be plain ASCII, {limit} characters or fewer")
    return text


def _int(value, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be a whole number")
    return value


def load_config(path: Path | None = None) -> dict:
    path = Path(path) if path else CONFIG_PATH
    if not path.exists():
        raise FileNotFoundError(
            "Copy config.example.json to config.json and fill in the game folder and account."
        )
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("config.json must be an object")

    name = _ascii(raw.get("character_name") or "Lira", "character_name", 16, allow_empty=False)
    account = _ascii(raw.get("account"), "account", 16)
    password = _ascii(raw.get("password"), "password", 16)
    guild = str(raw.get("guild_card") or "").strip()
    if guild and (not guild.isdigit() or len(guild) > 12):
        raise ValueError("guild_card must be empty or digits")

    window_raw = raw.get("window") or {}
    if not isinstance(window_raw, dict):
        raise ValueError("window must be an object")
    window = {
        "x": _int(window_raw.get("x", 100), "window.x"),
        "y": _int(window_raw.get("y", 100), "window.y"),
        "width": _int(window_raw.get("width", 1280), "window.width"),
        "height": _int(window_raw.get("height", 720), "window.height"),
    }
    if window["width"] < 320 or window["height"] < 240:
        raise ValueError("window is too small")

    llm_raw = raw.get("llm") or {}
    if not isinstance(llm_raw, dict):
        raise ValueError("llm must be an object")
    token = str(llm_raw.get("token") or "").strip()
    if any(ch in token for ch in "\r\n"):
        raise ValueError("llm.token must be one line")
    base_url = str(llm_raw.get("base_url") or "https://api.openai.com/v1").strip()
    llm = {
        "base_url": base_url or "https://api.openai.com/v1",
        "model": str(llm_raw.get("model") or "").strip(),
        "token": token,
    }
    return {
        "character_name": name,
        "account": account,
        "password": password,
        "guild_card": guild,
        "game_dir": str(raw.get("game_dir") or "").strip(),
        "chat_log_dir": str(raw.get("chat_log_dir") or "").strip(),
        "window": window,
        "llm": llm,
    }


def conversation_on(cfg: dict) -> bool:
    llm = cfg.get("llm") or {}
    return bool(str(llm.get("token") or "").strip() and str(llm.get("model") or "").strip())


def describe(cfg: dict) -> list[str]:
    """Status lines safe to print. Password and token are omitted."""

    lines = [
        f"character: {cfg['character_name']}",
        f"account: {cfg['account'] or '(not set)'}",
        f"game_dir: {cfg['game_dir'] or '(not set)'}",
        f"chat_log_dir: {cfg['chat_log_dir'] or '(uses the game folder log)'}",
    ]
    token = str(cfg["llm"].get("token") or "").strip()
    if conversation_on(cfg):
        lines.append(f"conversation: on ({cfg['llm']['model']})")
    elif token:
        lines.append("conversation: off (set llm.model as well as the token)")
    else:
        lines.append("conversation: off")
    return lines


def write_launch_cfg(cfg: dict, dest: Path) -> None:
    win = cfg["window"]
    text = "\n".join(
        [
            f"game_dir={cfg['game_dir']}",
            f"account={cfg['account']}",
            f"password={cfg['password']}",
            f"character={cfg['character_name']}",
            f"window={int(win['x'])},{int(win['y'])},{int(win['width'])},{int(win['height'])}",
            "",
        ]
    )
    dest.write_text(text, encoding="utf-8")
