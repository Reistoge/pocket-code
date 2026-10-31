# pocket-code

A tiny terminal coding chat that talks to **local models through
[Ollama](https://ollama.com)**. Pick a few files from the current directory,
pick a model, and ask questions — no API keys, no cloud, nothing leaves your
machine, simple and easy to use.

```
> /ask how do I reverse a list in python?

Response:
Use slicing: my_list[::-1]
```

## Requirements

- Python 3.9+
- [Ollama](https://ollama.com/download) installed and running (`ollama serve`)
- At least one model pulled, e.g. `ollama pull llama3.1:8b`

## Install

The install puts a `pocket-code` command on your `PATH`, so you can run it from
any directory — like `opencode` or `git`.

```bash
# isolated install, recommended
uv tool install git+https://github.com/Reistoge/pocket-code
# or
pipx install git+https://github.com/Reistoge/pocket-code
```

From a local clone:

```bash
git clone https://github.com/Reistoge/pocket-code
cd pocket-code
uv tool install .
```

Then:

```bash
cd ~/my-project
pocket-code
```

## Usage

Run `pocket-code` inside a project. It asks which files to use as context, then
which model to use. The model choice is remembered, so the next run starts
straight away. Files in subdirectories are listed too, labelled by their path
relative to where you run it (e.g. `src/app/config.py`).

| Command     | What it does                                              |
|-------------|-----------------------------------------------------------|
| `/files`    | Change which files are loaded as context                  |
| `/models`   | Switch model (the old one is unloaded to free VRAM)       |
| `/profile`  | Switch the system instructions profile                    |
| `/view`     | Show loaded files and token count                         |
| `/clear`    | Forget file context and conversation history              |
| `/ask <q>`  | Ask a general question, ignoring the loaded files         |
| `/exit`     | Quit (also `exit`, `bye`, or `Ctrl+C`)                    |

Keybindings:

- `Enter` sends the message
- `Alt+Enter` adds a new line
- `Ctrl+C` while the model is typing stops the current generation

Flags:

```bash
pocket-code --ask            # skip file selection, defaults to the "general" profile
pocket-code --change-model   # re-prompt for the model even if one is saved
```

## System instruction profiles

The system prompt comes from named profiles in
`~/.config/pocket-code/config.json`. The file is created on first run with two
profiles, `coding` and `general`; add or edit as many as you like:

```json
{
  "last_model": "llama3.1:8b",
  "last_profile": "coding",
  "profiles": {
    "coding": "You are a coding assistant. Keep answers concise and code-focused.",
    "general": "Keep answers concise, the answer can be of any topic or knowledge.",
    "reviewer": "You are a strict code reviewer. Point out bugs and edge cases first."
  }
}
```

- `/profile` swaps the active profile mid-session; the choice is remembered
  for the next run.
- The selected profile's text is always sent as the system prompt. When files
  are loaded, their contents are appended to it — except for `/ask`, which
  ignores file context.
- Edit the JSON while pocket-code is running and the change shows up the next
  time you start it.

## How it works

1. Reads the files you select into a single context block.
2. Warns you if the context is close to the 8000-token budget.
3. Sends the context plus your conversation history to Ollama and streams the
   reply back, rendered as Markdown.
4. Unloads the model when you exit so your VRAM is freed.

Your model preference is stored in `~/.config/pocket-code/config.json`.

## License

MIT
