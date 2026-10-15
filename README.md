# Lira

Lira is a FOnewearl partner for Phantasy Star Online Blue Burst. This repo is her client: a second game window, a chat listener, and the brain that answers.

She logs into an account you create, then talks in party chat. The first person who speaks to her is the one she listens to after that.

## What you need

- Windows
- Python 3.11 or newer
- Visual Studio with the C++ desktop tools, used once to build her input hook
- A Blue Burst install that contains `psobb.exe` and writes a daily chat log at `log\chatYYYYMMDD.txt`
- A server you can already reach from that install

This repo does not include the game, a server address, or an account.

## Create her account

Make a new account in the game, the same way you make your own. Blue Burst logins are up to 16 characters, plain ASCII.

That account is only a login. It starts with no character. Lira does not make the character herself.

## Configure

Copy `config.example.json` to `config.json` in this folder. `config.json` stays on your machine. Do not commit it.

```json
{
  "character_name": "Lira",
  "account": "her-login",
  "password": "her-password",
  "guild_card": "",
  "game_dir": "C:\\Path\\To\\Your\\PSOBB",
  "chat_log_dir": "",
  "window": {"x": 100, "y": 100, "width": 1280, "height": 720},
  "llm": {
    "base_url": "https://api.openai.com/v1",
    "model": "",
    "token": ""
  }
}
```

| Field | Purpose |
| --- | --- |
| `character_name` | The character she speaks as. The default is `Lira`. Chat from this name is ignored so she does not answer herself. |
| `account` | The login you created for her. Required. |
| `password` | Typed for her at the title screen. Leave it empty to type the password yourself in her window. |
| `guild_card` | Optional. If set, chat from that guild card is ignored along with her name. |
| `game_dir` | The folder that contains `psobb.exe`. |
| `chat_log_dir` | Optional. Empty uses `game_dir\log`. |
| `window` | Where her window opens. The default is on the main display. |
| `llm.base_url` | An OpenAI-compatible API root, ending in `/v1`. |
| `llm.model` | The model name that endpoint expects. |
| `llm.token` | Your own key. Empty leaves conversation off. |

Check the file without printing the password or the token:

```text
python run.py --check
```

## Build

From `client`:

```text
build.bat
```

That produces `lira_hook.dll` and `lira_launch.exe` next to the sources. Build output is not part of the repo.

## Create her character

1. Start her client:

   ```text
   python run.py --launch
   ```

   The launcher opens `psobb.exe`, injects the hook, and types the account from `config.json`. If `password` is set, it submits the login. Your own saved PSOBB login is copied aside for that start and put back afterward. The launcher does not read or print the saved password.

2. In her window, create the character yourself. Name her `Lira` and choose FOnewearl. That name and class land on Pinkal. Use the same spelling as `character_name`.

3. Leave her in the lobby. The same command keeps watching the chat log after the client is up.

The next time you run `--launch`, she logs into the character you already made. She still does not click through character creation, ship menus, or a quest counter.

If her client is already open and logged in, listen without starting another one:

```text
python run.py
```

Stop either command with Ctrl+C. Closing the terminal does not close her game window.

## Talking to her

Say these in party chat. Word choice can vary. `hold` and `wait` are the same order.

| You say | She does |
| --- | --- |
| hold, wait, stay, stop | Holds behind you |
| fight, engage, attack, go | Clears the hold |
| closer, come in | Steps her follow distance in |
| further, back up | Gives you room |
| shifta | Marks Shifta |
| deband | Marks Deband |
| heal, resta | Marks Resta |
| status, hp, pp | Reports the latest fight snapshot |

Other sentences get a short reminder of that list.

Those orders are stored for her decision brain. This client types chat. It does not walk her around or cast techniques. `status` says `No fight data yet` until a fight snapshot is supplied, and she uses that line for HP and PP.

She answers one hunter. The first person who talks to her locks that in for the session. Later lines from anyone else are ignored.

## Conversation token

Orders and status work with `llm.token` left empty.

Set `llm.token` and `llm.model` when you want her to answer normal sentences. The request is `POST {base_url}/chat/completions` with the token sent only as a Bearer header. A local server that ignores auth still needs some non-empty token, or conversation stays off.

With the token on, a normal sentence can become one of the orders above, and that order is stored. She is instructed to claim only the order she set: no walking off, no attacks, no menus, and no client or server edits. If the request fails, she drops back to the order list.

`python run.py --check` reports `conversation: on` or `conversation: off`. It never prints the token.

## Tests

```text
python -m unittest discover -s partner -p test_*.py
python -m unittest test_stack.py
```
