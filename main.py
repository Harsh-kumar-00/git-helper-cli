from __future__ import annotations

from utils import (
    command_needs_confirmation,
    format_command,
    generate_commit_message,
    get_current_branch,
    get_git_subcommand,
    get_next_suggestion,
    resolve_git_command,
    run_git_command,
    suggest_git_actions,
)


HELP_TEXT = """Commands:
  /help               Show this help message
  /suggest            Suggest a commit message and next git action
  /exit               Quit the program

Predefined git commands:
  status              git status
  init repo           git init
  add all             git add .
  commit <message>    git commit -m "<message>"
  push                git push
  pull                git pull

Anything else is sent to OpenRouter and converted into a git command.
Set OPENROUTER_API_KEY to enable AI parsing.
Optional: OPENROUTER_MODEL, OPENROUTER_HTTP_REFERER, OPENROUTER_APP_NAME
"""


def main() -> None:
    print("Git Helper CLI")
    print('Type /help for commands or /exit to quit.')

    while True:
        try:
            user_input = input(">>> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if not user_input:
            continue

        lowered = user_input.lower()

        if lowered == "/help":
            print(HELP_TEXT)
            continue

        if lowered == "/suggest":
            try:
                commit_message, next_action = suggest_git_actions()
                print(f"Suggested commit message: {commit_message}")
                print(f"Suggested next action: {next_action}")
            except ValueError as exc:
                print(f"Error: {exc}")
            print()
            continue

        if lowered == "/exit":
            print("Bye!")
            break

        try:
            if lowered == "commit":
                commit_message = generate_commit_message()
                command = ["git", "commit", "-m", commit_message]
            else:
                command, _source = resolve_git_command(user_input)

            if command_needs_confirmation(command):
                if not _confirm_execution():
                    print("Cancelled.")
                    print()
                    continue

            print(f"Executing: {format_command(command)}")

            success, output = run_git_command(command)
            if success:
                if output:
                    print(output)
                if get_git_subcommand(command) == "status":
                    branch = get_current_branch()
                    if branch:
                        print(f"Branch: {branch}")
                print("✔ Command successful")
            else:
                if output:
                    print(f"Error:\n{output}")
                print("❌ Command failed")

            print(f"💡 Suggestion: {get_next_suggestion(command, success, output)}")
        except ValueError as exc:
            print(f"Error: {exc}")
            print("❌ Command failed")
            print("💡 Suggestion: Try a built-in git command or rephrase the request.")

        print()


def _confirm_execution() -> bool:
    try:
        answer = input("Are you sure? (y/n): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False

    return answer == "y"


if __name__ == "__main__":
    main()
