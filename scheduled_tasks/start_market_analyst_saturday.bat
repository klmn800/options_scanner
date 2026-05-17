@echo off
REM Market Analyst — Saturday Closure Session
REM Scheduled via Windows Task Scheduler (Saturdays)
REM
REM Two-step launch (same pattern as research).

cd /d E:\options_scanner

REM Step 1: Prepare the session prompt with date injection
python agents\market_analyst\launcher.py --prompt PROMPT_SATURDAY.md --prepare-only

REM Step 2: Launch Claude Code in a visible window
cd /d E:\options_scanner\agents\market_analyst
start "Market Analyst (Saturday)" cmd /k "claude --permission-mode auto @.session_prompt.md"
