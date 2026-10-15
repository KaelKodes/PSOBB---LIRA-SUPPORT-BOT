import tempfile
import unittest
from pathlib import Path

from chat_bridge import interpret, split_chat
from force_brain import Action, Enemy, Fighter, Snapshot
from self_update import PatchError, SelfPatcher
from identity import section_id
from session import Session


def quiet(**overrides) -> Snapshot:
    base = dict(
        me=Fighter(hp_ratio=0.9, shifta=True, deband=True),
        partner=Fighter(hp_ratio=0.8, shifta=True, deband=True),
        enemies=(Enemy(id=1, threat=10, defense_down=True, attack_down=True),),
        partner_has_aggro=True,
        in_bubble=True,
        flanking=True,
        has_drain_weapon=True,
        pp_ratio=0.5,
    )
    base.update(overrides)
    return Snapshot(**base)


class ChatTest(unittest.TestCase):
    def test_long_reply_splits_and_stops(self):
        lines = split_chat("word " * 80)
        self.assertLessEqual(len(lines), 4)
        self.assertTrue(all(len(line) <= 48 for line in lines))
        self.assertTrue(lines[-1].endswith("..."))

    def test_hunter_lock_and_own_voice_are_ignored(self):
        session = Session(root=Path(tempfile.mkdtemp()), hunter="Hunter")
        self.assertEqual(session.on_chat("Lira", "hold"), [])
        self.assertEqual(section_id("Lira"), "Pinkal")
        self.assertEqual(session.on_chat("Stranger", "hold"), [])
        self.assertEqual(session.on_chat("Hunter", "hold"), ["Holding behind you."])
        self.assertTrue(session.orders.hold)

    def test_hold_still_heals(self):
        session = Session(root=Path(tempfile.mkdtemp()), hunter="Hunter")
        session.on_chat("Hunter", "wait")
        snap = quiet(partner=Fighter(hp_ratio=0.2, shifta=True, deband=True))
        choice = session.step(snap)
        self.assertEqual(choice.action, Action.RESTA)

    def test_status_uses_the_last_snapshot(self):
        session = Session(root=Path(tempfile.mkdtemp()), hunter="Hunter")
        session.step(quiet())
        self.assertEqual(session.on_chat("Hunter", "status"), ["You 80% HP. Me 90% HP, 50% PP."])

    def test_talk_lands_in_the_inbox(self):
        root = Path(tempfile.mkdtemp())
        session = Session(root=root, hunter="Hunter")
        reply = session.on_chat("Hunter", "Which door are you taking?")
        self.assertEqual(reply, [])
        self.assertEqual(session.take_pending_talk(), "Which door are you taking?")
        inbox = (root / "chat" / "inbox.jsonl").read_text(encoding="utf-8")
        self.assertIn("Which door are you taking?", inbox)

    def test_server_fix_is_refused(self):
        root = Path(tempfile.mkdtemp())
        session = Session(root=root, hunter="Hunter")
        reply = session.on_chat("Hunter", "fix the server drop rate")
        self.assertIn("Client and server", reply[0])

    def test_outbox_is_spoken_once(self):
        root = Path(tempfile.mkdtemp())
        session = Session(root=root, hunter="Hunter")
        chat = root / "chat"
        chat.mkdir()
        (chat / "outbox.jsonl").write_text(
            '{"text": "Take the left door. I will buff on the way in and stay behind you."}\n',
            encoding="utf-8",
        )
        spoken = session.take_outbox()
        self.assertEqual(len(spoken), 2)
        self.assertTrue(all(len(line) <= 48 for line in spoken))
        self.assertFalse((chat / "outbox.jsonl").exists())
        self.assertEqual(session.take_outbox(), [])


class PatchTest(unittest.TestCase):
    def test_partner_file_updates_when_checks_pass(self):
        root = Path(tempfile.mkdtemp())
        target = root / "spacing.py"
        target.write_text("DISTANCE = 28\n", encoding="utf-8")
        message = SelfPatcher(root).apply("spacing.py", "28", "24", lambda: True)
        self.assertIn("spacing.py", message)
        self.assertIn("24", target.read_text(encoding="utf-8"))

    def test_failed_check_restores_the_file(self):
        root = Path(tempfile.mkdtemp())
        target = root / "spacing.py"
        target.write_text("DISTANCE = 28\n", encoding="utf-8")
        with self.assertRaises(PatchError):
            SelfPatcher(root).apply("spacing.py", "28", "1", lambda: False)
        self.assertEqual(target.read_text(encoding="utf-8"), "DISTANCE = 28\n")

    def test_server_and_boundary_paths_are_refused(self):
        root = Path(tempfile.mkdtemp())
        (root / "self_update.py").write_text("FROZEN = True\n", encoding="utf-8")
        patcher = SelfPatcher(root)
        for relative in ("../newserv/release/system/config.json", "self_update.py", "client/game.exe"):
            with self.assertRaises(PatchError):
                patcher.resolve(relative)

    def test_pending_patch_failure_is_spoken(self):
        root = Path(tempfile.mkdtemp())
        session = Session(root=root, hunter="Hunter")
        chat = root / "chat"
        chat.mkdir()
        (chat / "pending_patch.json").write_text(
            '{"file": "../newserv/system/config.json", "old": "a", "new": "b"}',
            encoding="utf-8",
        )
        spoken = session.apply_pending_patch()
        self.assertTrue(spoken)
        self.assertIn("left my code", spoken[0])
        self.assertFalse((chat / "pending_patch.json").exists())


if __name__ == "__main__":
    unittest.main()
