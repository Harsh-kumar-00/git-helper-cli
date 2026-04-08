# Git Helper CLI

Git Helper CLI is a lightweight terminal app that turns natural-language requests
into safe git commands, plus offers commit message suggestions and next-action tips
powered by OpenRouter.

## Features
- Convert plain-English requests into validated git commands
- Built-in shortcuts for common git tasks
- AI-generated commit messages from your repo state
- Suggested next actions after each command
- Safety checks and confirmations for risky operations

## Requirements
- Python 3.9+
- Git installed and available on your PATH
- OpenRouter API key

## Installation
```bash
git clone https://github.com/Harsh-kumar-00/git-helper-cli.git
cd git-helper-cli
```

## Configuration
Set your OpenRouter key in one of these ways:
- In-app: run `/setkey <your_api_key>`
- Environment variable: `OPENROUTER_API_KEY`

Optional environment variables:
- `OPENROUTER_MODEL` (default: `openrouter/auto`)
- `OPENROUTER_APP_NAME` (default: `Git Helper CLI`)
- `OPENROUTER_HTTP_REFERER`

The `/setkey` command stores your key in `~/.git-helper-cli.json`.

## Usage
Start the CLI:
```bash
python main.py
```

Type `/help` to see commands, or enter plain-English prompts such as:
- `show me the status`
- `create a new branch named feature/login`
- `rebase current branch onto main`

### Slash Commands
- `/help` — Show help
- `/suggest` — Suggest a commit message and next git action
- `/undo` — Undo last local commit (`git reset HEAD~1`)
- `/diff` — Show git diff
- `/clear` — Clear the terminal
- `/setkey <key>` — Save the OpenRouter API key
- `/exit` — Quit the program

### Predefined Commands
- `status` → `git status`
- `init repo` → `git init`
- `add all` → `git add .`
- `commit <message>` → `git commit -m "<message>"`
- `commit` → AI-generated commit message
- `push` → `git push`
- `pull` → `git pull`

Anything else is sent to OpenRouter and converted into a safe git command.

## Safety Notes
AI-generated commands are restricted to safe git subcommands (e.g., `status`,
`add`, `commit`, `push`, `pull`, `log`, `diff`, `branch`, `checkout`, `switch`,
`restore`, `stash`, `merge`, `rebase`). Commands like `push`, `pull`, and `reset`
require confirmation before execution.

## Troubleshooting
- **"OpenRouter API key is not set"**: run `/setkey <key>` or set `OPENROUTER_API_KEY`.
- **"Invalid or unsafe command generated"**: try rephrasing or use a built-in command.

## License
No license is currently specified in this repository. If you plan to distribute
or reuse this project, add a LICENSE file and update this section.
