@echo off
REM Trading Advisor — Sunday Housekeeping Session
REM Scheduled via Windows Task Scheduler (Sundays only)

cd /d E:\options_scanner

REM Step 1: Prepare the session prompt with date injection
python agents\trading_advisor\launcher.py --prompt PROMPT_SUNDAY.md --prepare-only

REM Step 2: Launch Claude Code in a visible window from agent workspace
cd /d E:\options_scanner\agents\trading_advisor
start "Trading Advisor (Sunday)" cmd /k "claude --permission-mode auto @.session_prompt.md"
