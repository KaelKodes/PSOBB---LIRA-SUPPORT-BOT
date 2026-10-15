"""Run Lira against a local Blue Burst client.

python run.py --check     show the config, without the password or token
python run.py --launch    start her client, then listen
python run.py             listen to a client that is already running
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PARTNER = ROOT / "partner"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(PARTNER) not in sys.path:
    sys.path.insert(0, str(PARTNER))

from chat_watch import LogTail, chat_path, parse_chat_line
from config_file import describe, load_config, write_launch_cfg
from conversation import respond
from llm import complete as llm_complete
from session import Session

PIPE = "\\\\.\\pipe\\LiraInput"


def pipe_cmd(line: str) -> str:
    with open(PIPE, "r+b", buffering=0) as handle:
        handle.write((line + "\n").encode("ascii"))
        data = b""
        while b"\n" not in data and len(data) < 512:
            chunk = handle.read(1)
            if not chunk:
                break
            data += chunk
    return data.decode("ascii", errors="replace").strip()


def say(text: str) -> None:
    safe = "".join(ch for ch in text if 32 <= ord(ch) < 127)[:48]
    if not safe:
        return
    try:
        pipe_cmd("tap space 80")
        time.sleep(0.3)
        pipe_cmd("text " + safe)
        time.sleep(0.15)
        pipe_cmd("tap enter 80")
    except OSError as err:
        print(f"could not speak ({err}): {safe}")
        return
    print("said: " + safe)


def launch_client(cfg: dict) -> None:
    if not cfg["account"]:
        raise SystemExit("Set account in config.json to the login she should use.")
    if not cfg["game_dir"]:
        raise SystemExit("Set game_dir in config.json to the folder that contains psobb.exe.")
    game = Path(cfg["game_dir"])
    if not (game / "psobb.exe").is_file():
        raise SystemExit(f"psobb.exe was not found in {game}")
    exe = ROOT / "client" / "lira_launch.exe"
    if not exe.is_file():
        raise SystemExit("Build the client first. Run client\\build.bat")
    cfg_path = ROOT / "client" / "launch.cfg"
    write_launch_cfg(cfg, cfg_path)
    try:
        result = subprocess.run([str(exe)], cwd=str(exe.parent))
    finally:
        cfg_path.unlink(missing_ok=True)
    if result.returncode != 0:
        raise SystemExit(f"launcher exited {result.returncode}")


def _fresh(seen: dict[str, float], key: str) -> bool:
    now = time.time()
    stale = [item for item, stamp in seen.items() if now - stamp > 4]
    for item in stale:
        del seen[item]
    if key in seen:
        return False
    seen[key] = now
    return True


def speak_lines(lines: list[str], last_reply: float) -> float:
    if not lines:
        return last_reply
    wait = 0.8 - (time.time() - last_reply)
    if last_reply and wait > 0:
        time.sleep(wait)
    for line in lines:
        say(line)
        time.sleep(0.35)
    return time.time()


def watch(cfg: dict, session: Session, complete) -> None:
    if not cfg["game_dir"] and not cfg["chat_log_dir"]:
        raise SystemExit("Set game_dir or chat_log_dir in config.json.")
    print("\n".join(describe(cfg)))
    history: list[dict] = []
    seen: dict[str, float] = {}
    tail = LogTail()
    announced: Path | None = None
    last_reply = 0.0
    while True:
        last_reply = speak_lines(session.take_outbox(), last_reply)
        last_reply = speak_lines(session.apply_pending_patch(), last_reply)
        path = chat_path(cfg)
        if path != announced:
            announced = path
            print("watching " + str(path))
        fresh = tail.read_new(path)
        if not fresh:
            time.sleep(0.4)
            continue
        for raw in fresh:
            parsed = parse_chat_line(raw, cfg["character_name"], cfg["guild_card"])
            if not parsed:
                continue
            sender, message = parsed
            if not _fresh(seen, sender + "\t" + message):
                continue
            lines = respond(session, cfg, sender, message, history, complete)
            last_reply = speak_lines(lines, last_reply)


def main(argv: list[str]) -> int:
    try:
        cfg = load_config()
    except (OSError, ValueError, FileNotFoundError) as err:
        print(err)
        return 1
    if "--check" in argv:
        print("\n".join(describe(cfg)))
        return 0
    if "--launch" in argv:
        launch_client(cfg)
    session = Session(root=PARTNER, bot_name=cfg["character_name"])

    def complete(messages):
        return llm_complete(cfg, messages)

    try:
        watch(cfg, session, complete)
    except KeyboardInterrupt:
        print("stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
