"""Chat replies.

Orders and status always come from the partner brain. Free-form lines are
answered by the conversation endpoint when a token and model are set. Without
that, she says which orders she can take and does not promise a later answer.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PARTNER = ROOT / "partner"
for entry in (str(ROOT), str(PARTNER)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from chat_bridge import split_chat
from config_file import conversation_on

ORDERS = ("hold", "fight", "closer", "further", "shifta", "deband", "resta")
CANNED = {
    "hold": "Holding behind you.",
    "fight": "Engaging.",
    "closer": "Moving in.",
    "further": "Giving you room.",
    "shifta": "Shifta.",
    "deband": "Deband.",
    "resta": "Resta.",
}
NO_TOKEN = (
    "Say hold, fight, closer, further, shifta, deband, resta, or status. "
    "A conversation token lets me answer other lines."
)
FAILED = (
    "I heard you. Conversation is down, so say hold, fight, closer, further, "
    "shifta, deband, resta, or status."
)
SYSTEM = """You are Lira, a FOnewearl in Phantasy Star Online Blue Burst, talking in party chat.
Reply with one JSON object and nothing else: {"say":"short line","order":null}
order is one of hold, fight, closer, further, shifta, deband, resta, or null.
The order field is the action. It is performed. Do not say you did anything you did not put in order.
Do not claim you walked, attacked, opened a menu, or changed the client or server.
Use the status in the player message for HP and PP. If it says there is no fight data, do not invent numbers.
Keep say under 120 characters, plain speech, no markup.
"""


def _clean(text: str) -> str:
    return " ".join(str(text).replace("\x00", " ").split())


def order_state(session) -> str:
    orders = session.orders
    flags = []
    if orders.hold:
        flags.append("hold")
    if orders.shifta:
        flags.append("shifta")
    if orders.deband:
        flags.append("deband")
    if orders.resta:
        flags.append("resta")
    if not flags:
        flags.append("none")
    return (
        f"orders={','.join(flags)} distance={orders.distance_scale:.2f} "
        f"status={session.status_line()}"
    )


def build_messages(session, sender: str, note: str, history: list[dict]) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM},
        *history,
        {"role": "user", "content": f"State: {order_state(session)}\n{sender} says: {note}"},
    ]


def parse_model_reply(raw: str) -> tuple[str, str | None]:
    text = _clean(raw)
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict):
            say = _clean(data.get("say") or "")
            order = data.get("order")
            if order is None or str(order).strip().lower() in ("", "null", "none"):
                return say, None
            order_name = str(order).strip().lower()
            if order_name not in ORDERS:
                order_name = None
            return say, order_name
    return text, None


def answer_talk(session, sender: str, note: str, cfg: dict, history: list[dict], complete) -> list[str]:
    if not conversation_on(cfg):
        return split_chat(NO_TOKEN)
    messages = build_messages(session, sender, note, history)
    try:
        raw = complete(messages)
    except Exception as err:
        print(f"conversation failed: {err}")
        return split_chat(FAILED)
    say, order = parse_model_reply(str(raw or ""))
    if order:
        session._apply_order(order)
        if not say:
            say = CANNED[order]
    if not say:
        return split_chat(FAILED)
    return split_chat(say)


def respond(session, cfg: dict, sender: str, text: str, history: list[dict], complete) -> list[str]:
    lines = list(session.on_chat(sender, text))
    pending = session.take_pending_talk()
    if pending is None:
        return lines
    spoken = answer_talk(session, sender, pending, cfg, history, complete)
    if spoken:
        history.append({"role": "user", "content": pending})
        history.append({"role": "assistant", "content": " ".join(spoken)})
        if len(history) > 8:
            del history[:-8]
    return spoken
