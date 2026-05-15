@echo off
REM Trading Advisor — Nightly Research Session
REM Scheduled via Windows Task Scheduler (nightly, evening)
REM
REM Two-step launch:
REM   1. Python launcher injects date/time into prompt, writes .session_prompt.md
REM   2. Claude Code launches in a visible window from the agent workspace

cd /d E:\options_scanner

REM Step 1: Prepare the session prompt with date injection
python agents\trading_advisor\launcher.py --prompt PROMPT_RESEARCH.md --prepare-only

REM Step 2: Launch Claude Code in a visible window
cd /d E:\options_scanner\agents\trading_advisor
start "Trading Advisor Research" cmd /k "claude --permission-mode auto @.session_prompt.md"
