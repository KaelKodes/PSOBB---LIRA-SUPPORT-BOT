"""Ultima's daily chat log.

Lines are tab-separated UTF-16: time, guild card, character, message.
Her own name, and her guild card when one is configured, are skipped.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path


def chat_path(cfg: dict, moment: datetime | None = None) -> Path:
    moment = moment or datetime.now()
    folder = cfg.get("chat_log_dir") or str(Path(cfg.get("game_dir") or "") / "log")
    return Path(folder) / moment.strftime("chat%Y%m%d.txt")


def decode_log(blob: bytes) -> str:
    text = blob.decode("utf-16-le", errors="ignore")
    if text.startswith("\ufeff"):
        text = text[1:]
    return text


class LogTail:
    """Reads new complete lines. A short write is kept until the newline arrives."""

    def __init__(self):
        self.path: Path | None = None
        self.offset = 0
        self.pending = ""

    def read_new(self, path: Path) -> list[str]:
        if path != self.path:
            self.path = path
            self.pending = ""
            self.offset = path.stat().st_size if path.exists() else 0
            return []
        if not path.exists():
            return []
        size = path.stat().st_size
        if size < self.offset:
            self.offset = 0
            self.pending = ""
        if size == self.offset:
            return []
        with path.open("rb") as handle:
            handle.seek(self.offset)
            blob = handle.read(size - self.offset)
        if len(blob) % 2 == 1:
            blob = blob[:-1]
        self.offset += len(blob)
        text = self.pending + decode_log(blob)
        if not text:
            return []
        if text.endswith(("\n", "\r")):
            self.pending = ""
            return text.splitlines()
        parts = text.splitlines()
        if len(parts) == 1:
            self.pending = parts[0]
            return []
        self.pending = parts[-1]
        return parts[:-1]


def parse_chat_line(line: str, character: str, guild: str) -> tuple[str, str] | None:
    parts = line.split("\t")
    if len(parts) < 4:
        return None
    seen_guild = parts[1].strip()
    name = parts[2].strip()
    message = " ".join("\t".join(parts[3:]).split())
    if not message or not name:
        return None
    if character and name.lower() == character.lower():
        return None
    if name.lower() == "enter":
        return None
    if guild and seen_guild == guild:
        return None
    return name, message
