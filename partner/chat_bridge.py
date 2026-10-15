"""Party chat between you and the Force.

Blue Burst chat bubbles are short, so replies are split before they are sent.
Messages from anyone except the locked hunter are ignored.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MAX_LINE = 48
MAX_LINES = 4

_COLOR = re.compile(r"\$[0-9A-Fa-f]{1,2}")
_PROTECTED = re.compile(
    r"\b(newserv|game client|pso client|the client|the server|server exe|client exe)\b",
    re.I,
)
_FIX = re.compile(r"\b(fix|update|patch|change)\b", re.I)
_HOLD = re.compile(r"\b(hold|wait|stay|stop)\b", re.I)
_FIGHT = re.compile(r"\b(fight|engage|attack|go)\b", re.I)
_CLOSER = re.compile(r"\b(closer|tighter|come in)\b", re.I)
_FURTHER = re.compile(r"\b(further|back up|backup|give me room)\b", re.I)
_STATUS = re.compile(r"\b(status|how are you|hp|pp)\b", re.I)


@dataclass(frozen=True)
class Heard:
    kind: str
    replies: tuple[str, ...] = ()
    order: str | None = None
    note: str = ""


def clean_chat(text: str) -> str:
    text = _COLOR.sub("", text)
    return " ".join(text.replace("\x00", " ").split())


def split_chat(text: str) -> list[str]:
    text = clean_chat(text)
    if not text:
        return []
    lines: list[str] = []
    while text:
        if len(text) <= MAX_LINE:
            lines.append(text)
            break
        cut = text.rfind(" ", 0, MAX_LINE + 1)
        if cut <= 0:
            cut = MAX_LINE
        lines.append(text[:cut].strip())
        text = text[cut:].strip()
        if len(lines) == MAX_LINES:
            if text and lines[-1]:
                room = MAX_LINE - 3
                lines[-1] = lines[-1][:room].rstrip() + "..."
            break
    return [line for line in lines if line]


def _strip_name(text: str, bot_name: str) -> str:
    if bot_name and text.lower().startswith(bot_name.lower()):
        text = text[len(bot_name) :].lstrip(" ,:-")
    return text


def interpret(sender: str, text: str, *, bot_name: str, hunter: str | None) -> Heard:
    """Classify one incoming chat line."""

    body = _strip_name(clean_chat(text), bot_name)
    if not body or sender.lower() == bot_name.lower():
        return Heard("ignore")
    if hunter and sender.lower() != hunter.lower():
        return Heard("ignore")

    if _FIX.search(body) and _PROTECTED.search(body):
        return Heard(
            "refused",
            tuple(split_chat("I can change my own code. Client and server updates stay with you.")),
            note=body,
        )
    if _FIX.search(body) and re.search(r"\b(yourself|your|spacing|brain|combo|buff)\b", body, re.I):
        return Heard(
            "fix",
            tuple(split_chat("Noted. I'll patch my own code after the checks pass.")),
            note=body,
        )
    if _STATUS.search(body):
        return Heard("status", order="status", note=body)
    if _HOLD.search(body):
        return Heard("order", tuple(split_chat("Holding behind you.")), order="hold", note=body)
    if _CLOSER.search(body):
        return Heard("order", tuple(split_chat("Moving in.")), order="closer", note=body)
    if _FURTHER.search(body):
        return Heard("order", tuple(split_chat("Giving you room.")), order="further", note=body)
    if re.search(r"\bshifta\b", body, re.I):
        return Heard("order", tuple(split_chat("Shifta.")), order="shifta", note=body)
    if re.search(r"\bdeband\b", body, re.I):
        return Heard("order", tuple(split_chat("Deband.")), order="deband", note=body)
    if re.search(r"\b(heal|resta)\b", body, re.I):
        return Heard("order", tuple(split_chat("Resta.")), order="resta", note=body)
    if _FIGHT.search(body):
        return Heard("order", tuple(split_chat("Engaging.")), order="fight", note=body)
    return Heard("talk", note=body)
