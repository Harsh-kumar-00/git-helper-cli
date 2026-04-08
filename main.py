from __future__ import annotations

import os

from utils import (
    APIError,
    CommandSafetyError,
    GitHelperError,
    command_needs_confirmation,
    format_command,
    generate_commit_message,
    get_current_branch,
    get_git_subcommand,
    get_next_suggestion,
    resolve_git_command,
    run_git_command,
    set_api_key,
    suggest_git_actions,
)

COLORS = {
    "GREEN": "\033[92m",
    "RED": "\033[91m",
    "YELLOW": "\033[93m",
    "CYAN": "\033[96m",
    "RESET": "\033[0m",
}

def print_color(text: str, color: str) -> None:
    """Print text with the specified ANSI color."""
    print(f"{COLORS.get(color, '')}{text}{COLORS['RESET']}")


HELP_TEXT = """Commands:
  /help               Show this help message
  /suggest            Suggest a commit message and next git action
  /undo               Undo the last local commit (git reset HEAD~1)
  /diff               Show git diff
  /clear              Clear the terminal screen
  /setkey <key>       Save the OpenRouter API key
  /exit               Quit the program

Predefined git commands:
  status              git status
  init repo           git init
  add all             git add .
  commit <message>    git commit -m "<message>"
  push                git push
  pull                git pull

Anything else is sent to OpenRouter and converted into a git command.
"""


def handle_help(args: str) -> bool:
    print(HELP_TEXT)
    return True

def handle_suggest(args: str) -> bool:
    try:
        commit_message, next_action = suggest_git_actions()
        print_color(f"Suggested commit message: {commit_message}", "CYAN")
        print_color(f"Suggested next action: {next_action}", "YELLOW")
    except GitHelperError as exc:
        print_color(f"Error: {exc}", "RED")
    print()
    return True

def handle_exit(args: str) -> bool:
    print("Bye!")
    return False

def handle_clear(args: str) -> bool:
    os.system('cls' if os.name == 'nt' else 'clear')
    return True

def handle_undo(args: str) -> bool:
    print_color("Undoing last commit...", "CYAN")
    success, output = run_git_command(["git", "reset", "HEAD~1"])
    if success:
        print_color("✔ Undo successful", "GREEN")
        if output:
            print(output)
    else:
        print_color("❌ Undo failed", "RED")
        if output:
            print_color(output, "RED")
    print()
    return True

def handle_diff(args: str) -> bool:
    success, output = run_git_command(["git", "diff"])
    if success and output:
        print(output)
    elif success:
        print_color("No changes to show.", "YELLOW")
    else:
        print_color(f"❌ Error running diff: {output}", "RED")
    print()
    return True

def handle_setkey(args: str) -> bool:
    if not args:
        print_color("Usage: /setkey <your_api_key>", "RED")
        return True
    set_api_key(args)
    print_color("✔ API key saved to ~/.git-helper-cli.json", "GREEN")
    print()
    return True

COMMAND_HANDLERS = {
    "/help": handle_help,
    "/suggest": handle_suggest,
    "/exit": handle_exit,
    "/clear": handle_clear,
    "/undo": handle_undo,
    "/diff": handle_diff,
    "/setkey": handle_setkey,
}


def main() -> None:
    print_color("Git Helper CLI", "CYAN")
    print('Type /help for commands or /exit to quit.')

    while True:
        branch = get_current_branch()
        prompt_prefix = f"({branch}) " if branch else ""
        
        try:
            user_input = input(f"{COLORS['CYAN']}{prompt_prefix}>>>{COLORS['RESET']} ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if not user_input:
            continue

        # Handle slash commands
        if user_input.startswith("/"):
            parts = user_input.split(maxsplit=1)
            cmd = parts[0].lower()
            args = parts[1] if len(parts) > 1 else ""
            
            handler = COMMAND_HANDLERS.get(cmd)
            if handler:
                should_continue = handler(args)
                if not should_continue:
                    break
                continue
            else:
                print_color(f"Unknown command: {cmd}", "RED")
                continue

        # Handle normal git/ai commands
        try:
            if user_input.lower() == "commit":
                commit_message = generate_commit_message()
                command = ["git", "commit", "-m", commit_message]
            else:
                command, _source = resolve_git_command(user_input)

            if command_needs_confirmation(command):
                if not _confirm_execution(command):
                    print_color("Cancelled.", "YELLOW")
                    print()
                    continue

            print(f"Executing: {COLORS['CYAN']}{format_command(command)}{COLORS['RESET']}")

            success, output = run_git_command(command)
            if success:
                if output:
                    print(output)
                
                # Show branch if status
                if get_git_subcommand(command) == "status":
                    branch = get_current_branch()
                    if branch:
                        print_color(f"Branch: {branch}", "CYAN")

                print_color("✔ Command successful", "GREEN")
            else:
                if output:
                    print_color(f"Error:\n{output}", "RED")
                print_color("❌ Command failed", "RED")

            print(f"💡 Suggestion: {COLORS['YELLOW']}{get_next_suggestion(command, success, output)}{COLORS['RESET']}")

        except CommandSafetyError as exc:
            print_color(f"Safety Error: {exc}", "RED")
        except APIError as exc:
            print_color(f"API Error: {exc}", "RED")
        except GitHelperError as exc:
            print_color(f"Error: {exc}", "RED")
            print_color("❌ Command failed", "RED")
            print_color("💡 Suggestion: Try a built-in git command or rephrase the request.", "YELLOW")
        except Exception as exc:
            print_color(f"Unexpected Error: {exc}", "RED")

        print()


def _confirm_execution(command: list[str]) -> bool:
    try:
        command_str = format_command(command)
        answer = input(f"Are you sure you want to run '{command_str}'? (y/n): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False

    return answer == "y"


if __name__ == "__main__":
    main()
