# Security

CookieRookie lets a language model read your files, change them and run commands on your machine. This page says what it can do, what stops it, and how to report a problem.

## What the agent can do

| Tool | What it does | Asks first? |
|------|--------------|-------------|
| `read_file`, `search_files`, `find_files` | Read files and folder listings | No |
| `edit_file`, `write_file` | Change or create files, inside the project folder only | Yes |
| `exec` | Run any shell command (`shell=True`, 30 s timeout by default) | Yes |
| `git_status`, `git_diff`, `git_log`, `git_branch` | Show the project's git state | No |
| `git_commit`, `git_checkout` | Commit, switch branches | Yes (interactive mode) |
| `test_run` | Run the project's tests (pytest, unittest, jest or go test) | **No** |
| `test_generate` | Read a source file and create the tests folder | No |

Things to know:

- **Interactive mode** (`python main.py --interactive`) pauses before every tool marked "Yes" and waits for `/confirm`, `/reject` or `/edit`. Read the arguments before you confirm: a confirmed `exec` runs exactly that command.
- **Debug mode** (`python main.py "bug"`) shows each edit and command and asks before running it. `--yes` turns the questions off: use it only on code you can restore (a clean git checkout) or in a container.
- **Running tests runs code.** `test_run` doesn't ask, and tests execute whatever the project's test files contain. Don't point CookieRookie at code you don't trust.
- `edit_file` and `write_file` refuse paths outside the folder CookieRookie was started in. Reading is not limited: the model can read any file your user account can access, and what it reads is sent to the API (below). `exec` runs with your user's rights, so a command can still touch anything; that's why it asks.

## What leaves your machine

- Every request sends the task, the tool results (file contents, command output, test output) and the history to the API at `ANTHROPIC_BASE_URL` (MiniMax by default). Don't use CookieRookie on files you may not share with that provider.
- Nothing else is sent anywhere.

## Your API key

- The key is read from `.env` in the CookieRookie folder, which is in `.gitignore`. Never commit it.
- It is sent only to `ANTHROPIC_BASE_URL`, in the `x-api-key` header.

## Safer setups

- Work in a git repository with no uncommitted changes, so `git diff` shows every change and `git checkout .` undoes them.
- For untrusted code, run CookieRookie inside a container or a throwaway VM.

## Reporting a vulnerability

Please don't post exploit details in a public issue. Use GitHub's private reporting (the repository's **Security** tab → **Report a vulnerability**) if it's available; otherwise open an issue that only says you have found a security problem, and the maintainer will contact you.
