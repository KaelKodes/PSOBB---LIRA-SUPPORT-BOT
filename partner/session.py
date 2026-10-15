"""In-game chat session.

Party chat is heard. Orders change this run immediately. A free-form line is
held for the conversation step, which answers it only when a token is set.
Replies dropped in the outbox are spoken on the next tick.

A self-fix is a JSON patch dropped in the chat folder. The bot applies it
only inside this package, then reloads. Client and server files are refused.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from chat_bridge import interpret, split_chat
from force_brain import ForceClass, Orders, Snapshot, decide, follow_distance
from identity import CHARACTER_CLASS, CHARACTER_NAME
from self_update import PatchError, SelfPatcher, run_partner_tests

DISTANCE_MIN = 0.45
DISTANCE_MAX = 2.0
DISTANCE_STEP = 0.25


@dataclass
class Mail:
    sender: str
    text: str
    kind: str


class Session:
    def __init__(
        self,
        root: Path | None = None,
        bot_name: str = CHARACTER_NAME,
        force: ForceClass = CHARACTER_CLASS,
        hunter: str | None = None,
    ):
        self.root = (root or Path(__file__).resolve().parent).resolve()
        self.chat_dir = self.root / "chat"
        self.bot_name = bot_name
        self.force = force
        self.hunter = hunter
        self.orders = Orders()
        self._last_snap: Snapshot | None = None
        self._pending_talk: str | None = None

    @property
    def distance(self) -> float:
        return follow_distance(self.force, self.orders)

    def on_chat(self, sender: str, text: str) -> list[str]:
        if self.hunter is None and sender.lower() != self.bot_name.lower() and text.strip():
            self.hunter = sender
        heard = interpret(sender, text, bot_name=self.bot_name, hunter=self.hunter)
        if heard.kind == "ignore":
            return []
        if heard.kind == "order":
            self._apply_order(heard.order or "")
            return list(heard.replies)
        if heard.kind == "status":
            return split_chat(self.status_line())
        if heard.kind == "talk":
            self._write_mail(Mail(sender, heard.note, "talk"))
            self._pending_talk = heard.note
            return []
        if heard.kind == "fix":
            self._write_mail(Mail(sender, heard.note, "fix"))
            return list(heard.replies)
        if heard.kind == "refused":
            self._write_mail(Mail(sender, heard.note, "refused"))
            return list(heard.replies)
        return []

    def step(self, snap: Snapshot):
        self._last_snap = snap
        choice = decide(snap, self.force, self.orders)
        if choice.reason == "you asked":
            if choice.action.value == "resta":
                self.orders.resta = False
            elif choice.action.value == "shifta":
                self.orders.shifta = False
            elif choice.action.value == "deband":
                self.orders.deband = False
        return choice

    def status_line(self) -> str:
        snap = self._last_snap
        if snap is None:
            return "No fight data yet."
        holding = " Holding." if self.orders.hold else ""
        return (
            f"You {snap.partner.hp_ratio:.0%} HP. "
            f"Me {snap.me.hp_ratio:.0%} HP, {snap.pp_ratio:.0%} PP."
            f"{holding}"
        )

    def take_pending_talk(self) -> str | None:
        note = self._pending_talk
        self._pending_talk = None
        return note

    def take_outbox(self) -> list[str]:
        path = self.chat_dir / "outbox.jsonl"
        if not path.exists():
            return []
        lines: list[str] = []
        for raw in path.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            item = json.loads(raw)
            lines.extend(split_chat(str(item.get("text", ""))))
        path.unlink()
        return lines

    def apply_pending_patch(self) -> list[str]:
        path = self.chat_dir / "pending_patch.json"
        if not path.exists():
            return []
        try:
            patch = json.loads(path.read_text(encoding="utf-8"))
            message = SelfPatcher(self.root).apply(
                str(patch["file"]),
                str(patch["old"]),
                str(patch["new"]),
                lambda: run_partner_tests(self.root),
            )
        except (PatchError, KeyError, OSError, json.JSONDecodeError) as error:
            failed = self.chat_dir / "pending_patch.failed.json"
            if path.exists():
                path.replace(failed)
            return split_chat(f"I left my code as it was. {error}")
        path.unlink(missing_ok=True)
        self._reload_brain()
        reason = str(patch.get("reason") or message)
        return split_chat(f"Updated my code. {reason}")

    def _apply_order(self, order: str) -> None:
        if order == "hold":
            self.orders.hold = True
        elif order == "fight":
            self.orders.hold = False
        elif order == "closer":
            self.orders.distance_scale = max(DISTANCE_MIN, self.orders.distance_scale - DISTANCE_STEP)
        elif order == "further":
            self.orders.distance_scale = min(DISTANCE_MAX, self.orders.distance_scale + DISTANCE_STEP)
        elif order == "shifta":
            self.orders.shifta = True
        elif order == "deband":
            self.orders.deband = True
        elif order == "resta":
            self.orders.resta = True

    def _write_mail(self, mail: Mail) -> None:
        self.chat_dir.mkdir(parents=True, exist_ok=True)
        path = self.chat_dir / "inbox.jsonl"
        line = json.dumps({"from": mail.sender, "text": mail.text, "kind": mail.kind})
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def _reload_brain(self) -> None:
        import importlib

        import force_brain

        importlib.reload(force_brain)
        global decide, follow_distance
        decide = force_brain.decide
        follow_distance = force_brain.follow_distance
        self.force = force_brain.ForceClass(self.force.value)
