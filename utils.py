from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import urllib.error
import urllib.request
from pathlib import Path


class GitHelperError(Exception):
    """Base exception for all git helper errors."""

class APIError(GitHelperError):
    """Raised when there's an issue communicating with the OpenRouter API."""

class CommandSafetyError(GitHelperError):
    """Raised when a generated command is deemed unsafe or invalid."""


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_OPENROUTER_MODEL = "openrouter/auto"
ALLOWED_AI_SUBCOMMANDS = {
    "status", "add", "commit", "push", "pull", "log", "diff", 
    "branch", "checkout", "switch", "restore", "stash", "merge", "rebase"
}
INVALID_AI_COMMAND_MESSAGE = "Invalid or unsafe command generated"


def get_api_key() -> str:
    """Retrieve the OpenRouter API key from environment or config file."""
    api_key = os.getenv("OPENROUTER_API_KEY")
    if api_key:
        return api_key

    config_path = Path.home() / ".git-helper-cli.json"
    if config_path.exists():
        try:
            with config_path.open("r", encoding="utf-8") as f:
                config = json.load(f)
                return config.get("openrouter_api_key", "")
        except json.JSONDecodeError:
            pass
    return ""


def set_api_key(api_key: str) -> None:
    """Save the OpenRouter API key to the config file."""
    config_path = Path.home() / ".git-helper-cli.json"
    config = {}
    if config_path.exists():
        try:
            with config_path.open("r", encoding="utf-8") as f:
                config = json.load(f)
        except json.JSONDecodeError:
            pass
            
    config["openrouter_api_key"] = api_key
    with config_path.open("w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)


def parse_predefined_command(user_input: str) -> list[str] | None:
    text = user_input.strip()
    lowered = text.lower()

    if lowered == "status":
        return ["git", "status"]

    if lowered == "init repo":
        return ["git", "init"]

    if lowered == "add all":
        return ["git", "add", "."]

    if lowered == "push":
        return ["git", "push"]

    if lowered == "pull":
        return ["git", "pull"]

    if lowered == "commit":
        raise GitHelperError("Use: commit <message>")

    if lowered.startswith("commit "):
        message = _normalize_commit_message(text[7:].strip())
        if not message:
            raise GitHelperError("Commit message cannot be empty.")
        return ["git", "commit", "-m", message]

    return None


def resolve_git_command(user_input: str) -> tuple[list[str], str]:
    predefined_command = parse_predefined_command(user_input)
    if predefined_command is not None:
        return predefined_command, "predefined"

    return natural_language_to_git_command(user_input), "ai"


def run_git_command(command: list[str]) -> tuple[bool, str]:
    success, stdout, stderr, returncode = _capture_command(command)

    if success:
        return True, _join_output(stdout, stderr)

    error_output = _join_output(stderr, stdout) or "Git command failed."
    if returncode not in {0, -1}:
        error_output = f"{error_output}\nExit code: {returncode}"

    return False, error_output


def command_needs_confirmation(command: list[str]) -> bool:
    if not command or command[0] != "git":
        return False

    confirm_commands = {"push", "pull", "reset"}
    index = 1

    while index < len(command):
        token = command[index]

        if token in confirm_commands:
            return True

        if token in {"-c", "--config-env"}:
            index += 2
            continue

        if token.startswith("-"):
            index += 1
            continue

        return False

    return False


def generate_commit_message() -> str:
    """Generate a commit message based on the current staged/unstaged changes."""
    context, has_changes = _build_git_context()
    if not has_changes:
        raise GitHelperError("No changes found to build a commit message from.")

    content = _call_openrouter(
        messages=[
            {
                "role": "system",
                "content": (
                    "You write professional git commit messages. Return JSON only in "
                    'this format: {"message":"..."} '
                    "Use one concise line, imperative mood, no quotes, and no trailing period."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Generate a git commit message from this repository state.\n\n"
                    f"{context}"
                ),
            },
        ],
        max_tokens=60,
    )

    parsed = _extract_json_object(content)
    message = _normalize_commit_message(str(parsed.get("message", "")).strip())
    if not message:
        raise APIError("OpenRouter did not return a commit message.")

    return message


def get_current_branch() -> str | None:
    success, stdout, _stderr, _returncode = _capture_command(["git", "branch", "--show-current"])
    branch = stdout.strip()
    if success and branch:
        return branch

    success, stdout, _stderr, _returncode = _capture_command(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"]
    )
    branch = stdout.strip()
    if success and branch:
        return branch

    return None


def get_next_suggestion(command: list[str], success: bool, output: str) -> str:
    if not success:
        return "Review the error and try the command again."

    subcommand = get_git_subcommand(command)
    output_lower = output.lower()

    if subcommand == "status":
        if "changes to be committed" in output_lower:
            return "Commit your staged changes."
        if "changes not staged for commit" in output_lower or "untracked files" in output_lower:
            return "Add files you want to include, then commit."
        return "Pull the latest changes or start your next edit."

    if subcommand == "add":
        return "Commit your staged changes."

    if subcommand == "commit":
        return "Push your commit to the remote."

    if subcommand == "push":
        return "Run status to confirm everything is synced."

    if subcommand == "pull":
        return "Review the latest changes and continue working."

    if subcommand == "init":
        return "Add files and make your first commit."

    return "Run status to review the repository state."


def suggest_git_actions() -> tuple[str, str]:
    """Suggest a commit message and a next practical git action."""
    context, _ = _build_git_context()
    content = _call_openrouter(
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a git assistant. Return JSON only in this format: "
                    '{"commit_message":"...","next_action":"..."} '
                    "The commit message should be concise and professional. "
                    "The next action should be one short, practical sentence."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Based on this repository state, suggest a commit message and the "
                    f"next git action.\n\n{context}"
                ),
            },
        ],
        max_tokens=120,
    )

    parsed = _extract_json_object(content)
    commit_message = _normalize_commit_message(
        str(parsed.get("commit_message", "")).strip()
    )
    next_action = str(parsed.get("next_action", "")).strip()

    if not commit_message:
        raise APIError("OpenRouter did not return a commit message suggestion.")

    if not next_action:
        raise APIError("OpenRouter did not return a next action suggestion.")

    return commit_message, next_action


def natural_language_to_git_command(user_input: str) -> list[str]:
    content = _call_openrouter(
        messages=[
            {
                "role": "system",
                "content": (
                    "You convert plain-English git requests into exactly one git "
                    "command. Return JSON only in this format: "
                    '{"command":"git ..."}'
                    ". Do not use markdown. Do not explain anything. "
                    "Always return a command that starts with git."
                ),
            },
            {"role": "user", "content": user_input},
        ],
        max_tokens=80,
    )
    command_text = _extract_command_text(content)
    return _validate_ai_command(command_text)


def format_command(command: list[str]) -> str:
    return subprocess.list2cmdline(command)


def get_git_subcommand(command: list[str]) -> str | None:
    if len(command) >= 2 and command[0] == "git":
        return command[1]
    return None


def _normalize_commit_message(message: str) -> str:
    if len(message) >= 2 and message[0] == message[-1] and message[0] in {"'", '"'}:
        return message[1:-1].strip()
    return message


def _capture_command(command: list[str]) -> tuple[bool, str, str, int]:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return False, "", "Git is not installed or not available on PATH.", -1
    except Exception as exc:
        return False, "", f"Failed to run command: {exc}", -1

    return (
        completed.returncode == 0,
        completed.stdout.strip(),
        completed.stderr.strip(),
        completed.returncode,
    )


def _build_git_context() -> tuple[str, bool]:
    status_ok, status_stdout, status_stderr, _ = _capture_command(["git", "status", "--sb"])
    if not status_ok:
        raise GitHelperError(_join_output(status_stderr, status_stdout) or "Could not read git status.")

    staged_ok, staged_stdout, staged_stderr, _ = _capture_command(
        ["git", "diff", "--cached", "--no-ext-diff", "--unified=0"]
    )
    if not staged_ok:
        raise GitHelperError(_join_output(staged_stderr, staged_stdout) or "Could not read staged diff.")

    unstaged_ok, unstaged_stdout, unstaged_stderr, _ = _capture_command(
        ["git", "diff", "--no-ext-diff", "--unified=0"]
    )
    if not unstaged_ok:
        raise GitHelperError(_join_output(unstaged_stderr, unstaged_stdout) or "Could not read working tree diff.")

    status_text = status_stdout or "No status output."
    staged_diff = _clip_text(staged_stdout or "No staged diff.")
    unstaged_diff = _clip_text(unstaged_stdout or "No unstaged diff.")
    has_changes = _status_has_changes(status_stdout) or bool(staged_stdout) or bool(unstaged_stdout)

    context = (
        f"Git status:\n{status_text}\n\n"
        f"Staged diff:\n{staged_diff}\n\n"
        f"Unstaged diff:\n{unstaged_diff}"
    )

    return context, has_changes


def _extract_message_content(data: dict) -> str:
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise APIError("OpenRouter returned an unexpected response format.") from exc


def _extract_command_text(content: str) -> str:
    cleaned = _clean_ai_content(content)

    try:
        parsed = json.loads(cleaned)
        command = str(parsed.get("command", "")).strip()
        if command:
            return command
    except json.JSONDecodeError:
        pass

    return cleaned.strip("` \n")


def _validate_ai_command(command_text: str) -> list[str]:
    cleaned = command_text.strip()
    if not cleaned or _contains_unsafe_shell_syntax(cleaned):
        raise CommandSafetyError(INVALID_AI_COMMAND_MESSAGE)

    try:
        command = shlex.split(cleaned)
    except ValueError as exc:
        raise CommandSafetyError(INVALID_AI_COMMAND_MESSAGE) from exc

    if len(command) < 2:
        raise CommandSafetyError(INVALID_AI_COMMAND_MESSAGE)

    if command[0] != "git":
        raise CommandSafetyError(INVALID_AI_COMMAND_MESSAGE)

    if command[1] not in ALLOWED_AI_SUBCOMMANDS:
        raise CommandSafetyError(INVALID_AI_COMMAND_MESSAGE)

    if any(token in {"&&", "||", ";", "|", "&"} for token in command):
        raise CommandSafetyError(INVALID_AI_COMMAND_MESSAGE)

    return command


def _call_openrouter(messages: list[dict[str, str]], max_tokens: int) -> str:
    api_key = get_api_key()
    if not api_key:
        raise GitHelperError(
            "OpenRouter API key is not set. Use /setkey <your_key> or set OPENROUTER_API_KEY env var."
        )

    payload = {
        "model": os.getenv("OPENROUTER_MODEL", DEFAULT_OPENROUTER_MODEL),
        "messages": messages,
        "temperature": 0,
        "max_tokens": max_tokens,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "X-OpenRouter-Title": os.getenv("OPENROUTER_APP_NAME", "Git Helper CLI"),
    }

    referer = os.getenv("OPENROUTER_HTTP_REFERER")
    if referer:
        headers["HTTP-Referer"] = referer

    request = urllib.request.Request(
        OPENROUTER_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise APIError(
            f"OpenRouter request failed with status {exc.code}: "
            f"{_extract_error_message(error_body)}"
        ) from exc
    except urllib.error.URLError as exc:
        raise APIError(f"Could not reach OpenRouter: {exc.reason}") from exc
    except Exception as exc:
        raise APIError(f"OpenRouter request failed: {exc}") from exc

    return _extract_message_content(data)


def _extract_json_object(content: str) -> dict:
    cleaned = _clean_ai_content(content)

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise APIError("OpenRouter returned invalid JSON.") from exc

    if not isinstance(parsed, dict):
        raise APIError("OpenRouter returned an unexpected JSON shape.")

    return parsed


def _clean_ai_content(content: str) -> str:
    cleaned = content.strip()
    cleaned = re.sub(r"^```[a-zA-Z0-9_+-]*\n", "", cleaned)
    cleaned = re.sub(r"\n```$", "", cleaned)
    return cleaned


def _contains_unsafe_shell_syntax(command_text: str) -> bool:
    unsafe_patterns = ("&&", "||", ";", "|", ">", "<", "`", "$(", "\n", "\r")
    return any(pattern in command_text for pattern in unsafe_patterns)


def _join_output(*parts: str) -> str:
    cleaned_parts = [part.strip() for part in parts if part and part.strip()]
    return "\n".join(cleaned_parts)


def _clip_text(text: str, limit: int = 6000) -> str:
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}\n...[truncated]..."


def _status_has_changes(status_text: str) -> bool:
    for line in status_text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("##"):
            return True
    return False


def _extract_error_message(raw_error: str) -> str:
    try:
        parsed = json.loads(raw_error)
    except json.JSONDecodeError:
        return raw_error.strip() or "Unknown error"

    if isinstance(parsed, dict):
        error = parsed.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if message:
                return str(message)
        message = parsed.get("message")
        if message:
            return str(message)

    return raw_error.strip() or "Unknown error"
