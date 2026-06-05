@echo off
REM Market Analyst — Nightly Research Session
REM Scheduled via Windows Task Scheduler (nightly, evening)
REM
REM Two-step launch:
REM   1. Python launcher injects date/time into prompt, writes .session_prompt.md
REM   2. Claude Code launches in a visible window from the agent workspace

cd /d E:\options_scanner

REM Step 1: Prepare the session prompt with date injection
python agents\market_analyst\launcher.py --prompt PROMPT.md --prepare-only

REM Step 2: Launch Claude Code as a tab in the existing Windows Terminal window.
REM wt tabs do NOT inherit this .bat's cwd, so the cd is folded into cmd /k.
wt -w 0 new-tab --title "Market Analyst Research" cmd /k "cd /d E:\options_scanner\agents\market_analyst && claude --permission-mode auto @.session_prompt.md"
