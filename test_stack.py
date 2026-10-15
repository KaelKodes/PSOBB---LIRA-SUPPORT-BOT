"""Checks for the shareable Lira stack."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "partner"))

from chat_watch import LogTail, decode_log, parse_chat_line
from config_file import conversation_on, describe, load_config, write_launch_cfg
from conversation import answer_talk, parse_model_reply, respond
from session import Session


def sample_config(**overrides) -> dict:
    cfg = {
        "character_name": "Lira",
        "account": "guest",
        "password": "pw-sample",
        "guild_card": "",
        "game_dir": "C:\\Games\\PSOBB",
        "chat_log_dir": "",
        "window": {"x": 100, "y": 100, "width": 1280, "height": 720},
        "llm": {"base_url": "https://api.openai.com/v1", "model": "", "token": ""},
    }
    cfg.update(overrides)
    return cfg


class ConfigTest(unittest.TestCase):
    def test_example_ships_with_secrets_empty(self):
        example = json.loads((ROOT / "config.example.json").read_text(encoding="utf-8"))
        self.assertEqual(example["account"], "")
        self.assertEqual(example["password"], "")
        self.assertEqual(example["guild_card"], "")
        self.assertEqual(example["llm"]["token"], "")
        self.assertFalse(conversation_on(load_config(ROOT / "config.example.json")))

    def test_summary_hides_password_and_token(self):
        cfg = sample_config()
        cfg["llm"] = {"base_url": "https://api.openai.com/v1", "model": "demo-model", "token": "secret-token"}
        text = "\n".join(describe(cfg))
        self.assertNotIn("pw-sample", text)
        self.assertNotIn("secret-token", text)
        self.assertIn("conversation: on (demo-model)", text)

    def test_missing_model_keeps_conversation_off(self):
        cfg = sample_config()
        cfg["llm"]["token"] = "secret-token"
        self.assertFalse(conversation_on(cfg))
        self.assertIn("model", "\n".join(describe(cfg)))

    def test_launch_file_is_a_temp_copy(self):
        dest = Path(tempfile.mkdtemp()) / "launch.cfg"
        write_launch_cfg(sample_config(), dest)
        text = dest.read_text(encoding="utf-8")
        self.assertIn("account=guest", text)
        self.assertIn("password=pw-sample", text)
        dest.unlink()


class ConversationTest(unittest.TestCase):
    def test_orders_work_without_a_token(self):
        called = False

        def complete(messages):
            nonlocal called
            called = True
            return "{}"

        session = Session(root=Path(tempfile.mkdtemp()), hunter="Hunter")
        lines = respond(session, sample_config(), "Hunter", "hold", [], complete)
        self.assertEqual(lines, ["Holding behind you."])
        self.assertTrue(session.orders.hold)
        self.assertFalse(called)

    def test_free_chat_does_not_promise_an_answer(self):
        session = Session(root=Path(tempfile.mkdtemp()), hunter="Hunter")
        lines = respond(session, sample_config(), "Hunter", "Which door are you taking?", [], lambda messages: "{}")
        blob = " ".join(lines)
        self.assertNotIn("I'll answer", blob)
        self.assertIn("status", blob)

    def test_token_performs_the_order_it_names(self):
        seen = []

        def complete(messages):
            seen.append(json.dumps(messages))
            return '{"say":"Shifta.","order":"shifta"}'

        cfg = sample_config()
        cfg["llm"] = {"base_url": "https://api.openai.com/v1", "model": "demo-model", "token": "secret-token"}
        session = Session(root=Path(tempfile.mkdtemp()), hunter="Hunter")
        lines = respond(session, cfg, "Hunter", "buff me", [], complete)
        self.assertEqual(lines, ["Shifta."])
        self.assertTrue(session.orders.shifta)
        self.assertNotIn("secret-token", seen[0])

    def test_unknown_order_is_ignored(self):
        say, order = parse_model_reply('{"say":"On my way across the map.","order":"teleport"}')
        self.assertIsNone(order)
        self.assertIn("map", say)

    def test_plain_text_does_not_invent_an_order(self):
        say, order = parse_model_reply("I can hear you.")
        self.assertEqual(say, "I can hear you.")
        self.assertIsNone(order)

    def test_failed_request_falls_back(self):
        def complete(messages):
            raise OSError("down")

        cfg = sample_config()
        cfg["llm"] = {"base_url": "https://api.openai.com/v1", "model": "demo-model", "token": "secret-token"}
        session = Session(root=Path(tempfile.mkdtemp()), hunter="Hunter")
        lines = answer_talk(session, "Hunter", "hello", cfg, [], complete)
        self.assertIn("Conversation is down", " ".join(lines))
        self.assertFalse(session.orders.hold)


class LogTest(unittest.TestCase):
    def test_own_lines_and_guild_are_skipped(self):
        self.assertIsNone(parse_chat_line("t\t1\tLira\thi", "Lira", ""))
        self.assertEqual(parse_chat_line("t\t1\tHunter\thold", "Lira", ""), ("Hunter", "hold"))
        self.assertIsNone(parse_chat_line("t\t99\tHunter\thi", "Lira", "99"))

    def test_utf16_log_decodes(self):
        raw = "t\t1\tHunter\thello".encode("utf-16-le")
        self.assertIn("Hunter", decode_log(raw))

    def test_partial_line_waits_for_the_newline(self):
        folder = Path(tempfile.mkdtemp())
        path = folder / "chat.txt"
        tail = LogTail()
        self.assertEqual(tail.read_new(path), [])
        path.write_bytes("t\t1\tHunter\thel".encode("utf-16-le"))
        self.assertEqual(tail.read_new(path), [])
        with path.open("ab") as handle:
            handle.write("lo\n".encode("utf-16-le"))
        self.assertEqual(tail.read_new(path), ["t\t1\tHunter\thello"])


class PrivacyTest(unittest.TestCase):
    def test_sources_do_not_carry_private_markers(self):
        markers = [
            "Ka" + "el",
            "Ky" + "le",
            "469315" + "975",
            "75.187" + ".147",
            "192.168" + ".1.240",
            "PSOBB_" + "K" + "aelHold",
            "prefer_" + "ka" + "el",
            "D:\\" + "K" + "ael",
            "player_" + "lira",
            "-19" + "20",
        ]
        skip_names = {"config.json", "launch.cfg"}
        offenders = []
        for path in ROOT.rglob("*"):
            if not path.is_file():
                continue
            if path.name in skip_names or path.suffix.lower() in {".exe", ".dll", ".obj", ".log", ".pid", ".pyc"}:
                continue
            if "__pycache__" in path.parts:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for marker in markers:
                if marker in text:
                    offenders.append(f"{path.relative_to(ROOT)}: {marker}")
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
