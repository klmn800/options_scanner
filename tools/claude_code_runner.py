"""
Claude Code Runner — Generic subprocess wrapper for Claude Code CLI.

Spawns Claude Code CLI sessions with a prompt, captures structured results
via a result file written by the session, and returns structured dicts.

Designed as reusable infrastructure: any agent or pipeline can use this
to route expensive LLM work through Claude Code (subscription) instead
of the API (per-token billing).

Usage:
    from tools.claude_code_runner import run_claude_task

    result = run_claude_task(
        prompt="Analyze this data and write JSON to {result_file}",
        result_file=Path("output/result.json"),
        timeout=600,
        log_dir=Path("output/sessions"),
        task_id="analysis_001",
    )
    if result["success"]:
        data = result["result"]  # Parsed JSON from result_file
"""

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path


def _merged_env(env: dict[str, str] | None) -> dict[str, str] | None:
    """Merge caller-supplied env vars onto the current process env.

    Returns None when `env` is None so subprocess.run / Popen falls
    through to its default of inheriting os.environ. Returns a new
    dict otherwise so caller mutations don't leak."""
    if env is None:
        return None
    merged = dict(os.environ)
    merged.update(env)
    return merged


_claude_available = shutil.which("claude") is not None
if not _claude_available:
    import warnings
    warnings.warn(
        "Claude Code CLI ('claude') not found in PATH. "
        "run_claude_task() will fail. Install from https://claude.ai/code",
        stacklevel=2,
    )


# Cached permission mode for this process. Starts at "auto"; the first
# piped run that fails triggers a one-shot retry with "bypassPermissions"
# and, if that succeeds, caches bypass for the rest of the session
# (both piped and windowed). Auto mode requires Max/Team/Enterprise/API
# tier and Claude Code v2.1.83+; on Pro tier or older CLIs the flag is
# rejected and we transparently fall back to the prior bypass behavior.
_mode_lock = threading.Lock()
_permission_mode = "auto"


def get_permission_mode() -> str:
    """Return the currently active --permission-mode value."""
    with _mode_lock:
        return _permission_mode


def _record_auto_failure(reason: str) -> None:
    """Latch bypassPermissions for the rest of this process."""
    global _permission_mode
    with _mode_lock:
        if _permission_mode == "auto":
            _permission_mode = "bypassPermissions"
            sys.stderr.write(
                f"[claude_code_runner] --permission-mode auto failed "
                f"({reason}). Falling back to bypassPermissions for "
                f"the rest of this session.\n"
            )


def run_claude_task(
    prompt: str = "",
    result_file: Path | None = None,
    timeout: int = 1800,
    cwd: Path = None,
    log_dir: Path = None,
    task_id: str = None,
    windowed: bool = False,
    parse_json: bool = True,
    model: str | None = None,
    session_id: str | None = None,
    initial_msg: str | None = None,
    wait_for_result: bool = True,
    title: str | None = None,
    resume: bool = False,
    env: dict[str, str] | None = None,
) -> dict:
    """
    Run a task via Claude Code CLI and collect the result.

    The prompt should instruct the session to write its output to
    `result_file`. After the session completes, this function reads
    that file (as JSON if parse_json=True, as plain text otherwise).

    Args:
        prompt:      Full prompt text to send to Claude Code.
        result_file: Path where the session should write its JSON result.
                     Unused (and may be None) when wait_for_result=False
                     or resume=True.
        timeout:     Max seconds to wait for the session (default 1800 = 30 min).
        cwd:         Working directory for the subprocess (default: project root).
        log_dir:     Directory for prompt/session logs (default: no logging).
        task_id:     Identifier for log filenames (default: "task").
        windowed:    If True, open in a visible console window (Windows).
                     Session output streams to the window instead of being
                     captured. Useful for watching sessions in real time.
        model:       Optional model alias or ID forwarded to `claude --model`.
                     Accepts CC aliases (sonnet, opus, haiku) or full IDs.
                     None / empty string = leave it off and let CC pick its
                     own default (governed by the user's `claude` config).
        session_id:  If set, passes `--session-id <uuid>` so the session
                     binds to this UUID (callers can `claude --resume <uuid>`
                     later). Windowed mode only.
        initial_msg: If set, the windowed CLI invocation uses this string
                     as the bare command-line message instead of the
                     `@prompt_file` form. The agent then reads the prompt
                     itself (e.g. `claude --session-id X "Your task is in
                     /path/to/prompt.md — read it and take it from there"`).
        wait_for_result:
                     If False, do NOT poll for `result_file` in windowed
                     mode — spawn and return immediately with
                     `{status: "spawned", session_id: <uuid>}`.
                     Fire-and-forget for sessions the user owns.
        title:       Custom .bat window title. Defaults to
                     "Claude Code - {task_id}".
        resume:      If True, the invocation uses `claude --resume <session_id>`
                     instead of starting fresh. `session_id` must be set.
                     - With windowed=True: opens a fresh console on the
                       resumed session (no prompt, no result file).
                       Implies wait_for_result=False.
                     - With windowed=False (piped): sends `prompt` via stdin
                       to the resumed session and reads `result_file` as
                       normal piped mode. Used by orchestrators that drive
                       multi-turn conversations from a single Python loop.
        env:         Additional environment variables to set on the spawned
                     subprocess. Merged into `os.environ` (caller wins on
                     overlap). Used by orchestrators that need to inject
                     guardrails the agent can't override (e.g. OLG_PROGRAMS
                     whitelist read by rag/query.py at import).

    Returns:
        dict with keys:
            result       — Parsed JSON from result_file, or None on failure /
                           fire-and-forget.
            session_id   — Claude Code session UUID. In piped mode, the
                           UUID CC chose; in windowed mode, the
                           caller-supplied `session_id` (when set).
            session_log  — Full stdout from the CLI session (empty in windowed mode).
            elapsed      — Wall-clock seconds.
            success      — True if result_file was written and parsed,
                           or if wait_for_result=False / resume=True
                           (those return on spawn).
            error        — Error message string, or None on success.
            status       — Present (= "spawned") only when
                           wait_for_result=False or resume=True.
    """
    if task_id is None:
        task_id = "task"

    if resume:
        if not session_id:
            raise ValueError("resume=True requires session_id")
        if windowed:
            # Windowed resume: just open the terminal on an existing
            # session UUID. No prompt, no result file, no poll.
            start = time.time()
            return _run_windowed_resume(
                session_id, cwd, log_dir, task_id, start, title, env
            )
        # else: piped resume falls through to the piped path below,
        # which writes a prompt file, sends stdin, and reads result_file.
        if result_file is None:
            raise ValueError("piped resume requires result_file")
    elif result_file is None:
        # All non-resume paths read or hand off a result_file. Catch the
        # caller bug early instead of writing to None.
        raise ValueError("result_file is required unless resume=True")

    result_file = Path(result_file)

    if log_dir:
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)

    prompt_file = (log_dir or Path.cwd()) / f"prompt_{task_id}.txt"
    prompt_file.parent.mkdir(parents=True, exist_ok=True)
    prompt_file.write_text(prompt, encoding="utf-8")

    if cwd is None:
        cwd = Path(__file__).resolve().parents[1]

    start = time.time()

    if windowed:
        return _run_windowed(prompt_file, result_file, timeout, cwd,
                             log_dir, task_id, start, parse_json, model,
                             session_id=session_id, initial_msg=initial_msg,
                             wait_for_result=wait_for_result, title=title,
                             env=env)
    else:
        return _run_piped(prompt, result_file, timeout, cwd,
                          log_dir, task_id, start, parse_json, model,
                          env=env,
                          resume_session_id=session_id if resume else None)


def _run_piped(prompt, result_file, timeout, cwd, log_dir, task_id, start,
               parse_json=True, model=None, env=None, resume_session_id=None):
    """Run claude in pipe mode — stdout captured as JSON, not visible.

    Tries the cached permission mode first. If auto fails on this run,
    retries once with bypassPermissions; on bypass success the failure
    is recorded so subsequent calls (piped and windowed) skip auto.

    When `resume_session_id` is set, adds `--resume <uuid>` to the cmd
    so the call continues an existing session instead of starting fresh.
    """
    mode = get_permission_mode()
    result = _run_piped_once(prompt, mode, result_file, timeout, cwd,
                             log_dir, task_id, start, parse_json, model,
                             env=env, resume_session_id=resume_session_id)

    if mode == "auto" and not result["success"]:
        # Treat any failure on the first auto-mode invocation as a
        # potential mode rejection (wrong tier, older CLI). Retry once
        # with bypass — if it works, latch the fallback. Worst-case
        # cost is one extra subprocess on the first failing call.
        fallback_start = time.time()
        fallback = _run_piped_once(prompt, "bypassPermissions", result_file,
                                   timeout, cwd, log_dir, task_id,
                                   fallback_start, parse_json, model,
                                   env=env,
                                   resume_session_id=resume_session_id)
        if fallback["success"]:
            _record_auto_failure(result.get("error") or "auto-mode subprocess failed")
            fallback["_used_fallback_mode"] = "bypassPermissions"
            return fallback

    return result


def _run_piped_once(prompt, mode, result_file, timeout, cwd, log_dir,
                    task_id, start, parse_json=True, model=None, env=None,
                    resume_session_id=None):
    """Single piped subprocess attempt with a specific permission mode."""
    cmd = ["claude", "-p", "--output-format", "json",
           "--permission-mode", mode]
    if model:
        cmd.extend(["--model", model])
    if resume_session_id:
        cmd.extend(["--resume", resume_session_id])
    try:
        proc = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
            cwd=str(cwd),
            env=_merged_env(env),
        )
        raw_stdout = proc.stdout or ""
        stderr = proc.stderr or ""

        # Parse JSON output to extract session_id and result text
        session_id = None
        session_log = raw_stdout
        try:
            cli_output = json.loads(raw_stdout)
            session_id = cli_output.get("session_id")
            session_log = cli_output.get("result", raw_stdout)
        except (json.JSONDecodeError, TypeError):
            pass  # Fall back to raw stdout

        if stderr:
            session_log += f"\n\n--- STDERR ---\n{stderr}"

    except subprocess.TimeoutExpired:
        elapsed = time.time() - start
        return {
            "result": None,
            "session_id": None,
            "session_log": "",
            "elapsed": elapsed,
            "success": False,
            "error": f"Timeout after {timeout}s",
        }

    except FileNotFoundError:
        elapsed = time.time() - start
        return {
            "result": None,
            "session_id": None,
            "session_log": "",
            "elapsed": elapsed,
            "success": False,
            "error": "Claude Code CLI ('claude') not found in PATH",
        }

    elapsed = time.time() - start

    if log_dir:
        session_file = log_dir / f"session_{task_id}.md"
        session_file.write_text(session_log, encoding="utf-8")

    result = _read_result(result_file, session_log, elapsed, parse_json)
    result["session_id"] = session_id
    return result


def _run_windowed(prompt_file, result_file, timeout, cwd, log_dir, task_id, start,
                  parse_json=True, model=None, session_id=None,
                  initial_msg=None, wait_for_result=True, title=None,
                  env=None):
    """Run claude in a visible console window — user watches output live.

    Two invocation shapes:
      - Default (`initial_msg=None`): `claude @<prompt_file>` — agent reads
        the prompt file directly. This is the original comparator/QC shape.
      - `initial_msg=<str>`: `claude "<initial_msg>"` — agent receives the
        short message as the opening user turn. The author-research pattern
        uses this with the message pointing at a prompt file the agent reads.

    When `session_id` is set, passes `--session-id <uuid>` so callers can
    `claude --resume <uuid>` later. When `wait_for_result=False`, spawns
    and returns immediately without polling for `result_file` — for
    sessions the user owns (author research/draft).
    """
    prompt_path = str(prompt_file.resolve())
    bat_dir = log_dir or prompt_file.parent
    bat_file = bat_dir / f"run_{task_id}.bat"
    model_flag = f' --model {model}' if model else ''
    session_flag = f' --session-id {session_id}' if session_id else ''
    bat_title = title or f"Claude Code - {task_id}"

    if initial_msg is not None:
        # Quote-escape any embedded double-quotes so the .bat doesn't
        # truncate the message at the first inner quote.
        escaped_msg = initial_msg.replace('"', '\\"')
        claude_cmd = (
            f'claude --permission-mode {get_permission_mode()}'
            f'{model_flag}{session_flag} "{escaped_msg}"'
        )
    else:
        claude_cmd = (
            f'claude --permission-mode {get_permission_mode()}'
            f'{model_flag}{session_flag} @{prompt_path}'
        )

    if wait_for_result:
        # Original polling shape: keep the launcher window open with cmd /k
        # so subprocess.run returns when the user closes the launcher
        # (or never, since polling drives completion).
        bat_file.write_text(
            f'@echo off\n'
            f'cd /d {cwd}\n'
            f'title {bat_title}\n'
            f'start "" cmd /k "{claude_cmd}"\n',
            encoding="utf-8",
        )
    else:
        # Fire-and-forget: the user owns the resulting window. Open
        # cmd /k directly so the title sticks and the window stays open
        # after the session ends; orchestrator returns immediately.
        bat_file.write_text(
            f'@echo off\n'
            f'cd /d {cwd}\n'
            f'title {bat_title}\n'
            f'{claude_cmd}\n'
            f'echo.\n'
            f'echo === Session complete ===\n'
            f'pause\n',
            encoding="utf-8",
        )

    if not wait_for_result:
        # Spawn detached so the launcher process doesn't block. CC's
        # own window is what the user interacts with.
        try:
            subprocess.Popen(
                ["cmd", "/c", str(bat_file)],
                cwd=str(cwd),
                creationflags=subprocess.CREATE_NEW_CONSOLE,
                env=_merged_env(env),
            )
        except Exception as e:
            elapsed = time.time() - start
            return {
                "result": None,
                "session_id": session_id,
                "session_log": "",
                "elapsed": elapsed,
                "success": False,
                "error": f"Could not spawn batch file: {e}",
                "status": "error",
            }
        return {
            "result": None,
            "session_id": session_id,
            "session_log": "(windowed mode — fire-and-forget; user owns the window)",
            "elapsed": time.time() - start,
            "success": True,
            "error": None,
            "status": "spawned",
        }

    try:
        subprocess.run(
            [str(bat_file)], shell=True, cwd=str(cwd),
            env=_merged_env(env),
        )
    except Exception as e:
        elapsed = time.time() - start
        return {
            "result": None,
            "session_id": session_id,
            "session_log": "",
            "elapsed": elapsed,
            "success": False,
            "error": f"Could not launch batch file: {e}",
        }

    deadline = start + timeout
    poll_interval = 5

    while time.time() < deadline:
        if result_file.exists():
            time.sleep(2)
            break
        time.sleep(poll_interval)
    else:
        elapsed = time.time() - start
        return {
            "result": None,
            "session_id": session_id,
            "session_log": "(windowed mode — output was in console window)",
            "elapsed": elapsed,
            "success": False,
            "error": f"Timeout after {timeout}s",
        }

    elapsed = time.time() - start
    result = _read_result(
        result_file,
        "(windowed mode — output was in console window)",
        elapsed,
        parse_json,
    )
    # Caller-supplied session_id is what's authoritative in windowed mode
    # (we don't capture the UUID CC chooses on its own when none is passed).
    result["session_id"] = session_id
    return result


def _run_windowed_resume(session_id, cwd, log_dir, task_id, start, title, env):
    """Open `claude --resume <session_id>` in a fresh console.

    No prompt, no result file. The session is whatever the user does
    inside the window. Used by the *_resume launchers (author research,
    author draft, QC judge) when the orchestrator needs to drop the user
    back into an existing CC session.
    """
    if cwd is None:
        cwd = Path(__file__).resolve().parents[1]
    bat_dir = log_dir or Path(cwd)
    if log_dir:
        Path(log_dir).mkdir(parents=True, exist_ok=True)
    bat_file = Path(bat_dir) / f"resume_{task_id}.bat"
    bat_title = title or f"Claude Code Resume - {task_id}"
    bat_file.write_text(
        f'@echo off\n'
        f'cd /d {cwd}\n'
        f'title {bat_title}\n'
        f'echo.\n'
        f'echo  Resuming session: {session_id}\n'
        f'echo.\n'
        f'claude --permission-mode {get_permission_mode()} --resume {session_id}\n'
        f'echo.\n'
        f'pause\n',
        encoding="utf-8",
    )
    try:
        subprocess.Popen(
            ["cmd", "/c", str(bat_file)],
            cwd=str(cwd),
            creationflags=subprocess.CREATE_NEW_CONSOLE,
            env=_merged_env(env),
        )
    except Exception as e:
        return {
            "result": None,
            "session_id": session_id,
            "session_log": "",
            "elapsed": time.time() - start,
            "success": False,
            "error": f"Could not spawn resume batch file: {e}",
            "status": "error",
        }
    return {
        "result": None,
        "session_id": session_id,
        "session_log": "(windowed resume — user owns the window)",
        "elapsed": time.time() - start,
        "success": True,
        "error": None,
        "status": "spawned",
    }


def _read_result(result_file, session_log, elapsed, parse_json=True):
    """Read and parse the result file. Shared by both modes."""
    if not result_file.exists():
        return {
            "result": None,
            "session_log": session_log,
            "elapsed": elapsed,
            "success": False,
            "error": f"Result file not created: {result_file}",
        }

    raw = result_file.read_text(encoding="utf-8")

    if not parse_json:
        return {
            "result": raw,
            "session_log": session_log,
            "elapsed": elapsed,
            "success": True,
            "error": None,
        }

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        return {
            "result": None,
            "session_log": session_log,
            "elapsed": elapsed,
            "success": False,
            "error": f"Invalid JSON in result file: {e}",
        }

    return {
        "result": parsed,
        "session_log": session_log,
        "elapsed": elapsed,
        "success": True,
        "error": None,
    }
