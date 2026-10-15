# Lira

Lira is a FOnewearl partner for Phantasy Star Online Blue Burst. She logs into the server on her own account and joins the lobby on that connection. You stay on your own game client.

She does not open a second copy of the game. A second window was tried and removed because it did not work.

## Account and character

Create an account for her on the server, the same way you create your own. Blue Burst logins are up to 16 characters, plain ASCII. Put that username and password in `config.json`.

That login is enough for her to come online. If the account has no character yet, the login creates one: a FOnewearl named Lira, which lands on Pinkal. If that character is already on the account, she uses it. You do not build the character by hand in another window.

## Configure

Copy `config.example.json` to `config.json`. That file stays on your machine. Do not commit it.

| Field | Purpose |
| --- | --- |
| `character_name` | The character she speaks as. The default is `Lira`. Chat from this name is ignored so she does not answer herself. |
| `account` | The login you created for her. |
| `password` | The password for that login. |
| `guild_card` | Optional. If set, chat from that guild card is ignored along with her name. |
| `llm.base_url` | An OpenAI-compatible API root, ending in `/v1`. |
| `llm.model` | The model name that endpoint expects. |
| `llm.token` | Your own key. Empty leaves conversation off. |

Check the file without printing the password or the token:

```text
python run.py --check
```

## Talking to her

The first person who talks to her is the one she listens to for that session.

These orders work with the token left blank:

| You say | She does |
| --- | --- |
| hold, wait, stay, stop | Holds |
| fight, engage, attack, go | Clears the hold |
| closer, come in | Steps her follow distance in |
| further, back up | Gives you room |
| shifta | Marks Shifta |
| deband | Marks Deband |
| heal, resta | Marks Resta |
| status, hp, pp | Reports the latest fight snapshot |

Any other sentence gets a short reminder of that list. She does not promise to answer it later.

`status` says `No fight data yet` until a fight snapshot is supplied. She uses that line for HP and PP.

## Conversation token

Set `llm.token` and `llm.model` when you want her to answer normal sentences. The request is `POST {base_url}/chat/completions`, and the token is sent only as a Bearer header. A local server that ignores auth still needs some non-empty token, or conversation stays off.

With the token on, a normal sentence can become one of the orders above, and that order is stored. She is instructed to claim only the order she set. If the request fails, she drops back to the order list.

`python run.py --check` reports `conversation: on` or `conversation: off`. It never prints the token.

## Tests

```text
python -m unittest discover -s partner -p test_*.py
python -m unittest test_stack.py
```

## Issues
Lira may or may not be invincible... (she totally is)
This can be used to kite and "cheese" enemies
However, I still find this gameplay more enjoyable than playing it solo

You still have to find her abilities, she does know them by default.
You can trade them to her and i believe you can drop them and tell her to pick it up.

The same can be said for her equipment, but truthfully, it doesnt matter much for her.

I havent got to spend as much time on this as I would like and hope to expand upon it greatly.
This is a very early build just to show what I have so far and allow others to test it out.
