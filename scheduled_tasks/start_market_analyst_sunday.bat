@echo off
REM Market Analyst — Sunday Housekeeping Session
REM Scheduled via Windows Task Scheduler (Sundays)
REM
REM Two-step launch (same pattern as research).

cd /d E:\options_scanner

REM Step 1: Prepare the session prompt with date injection
python agents\market_analyst\launcher.py --prompt PROMPT_SUNDAY.md --prepare-only

REM Step 2: Launch Claude Code as a tab in the existing Windows Terminal window.
REM wt tabs do NOT inherit this .bat's cwd, so the cd is folded into cmd /k.
wt -w 0 new-tab --title "Market Analyst (Sunday)" cmd /k "cd /d E:\options_scanner\agents\market_analyst && claude --permission-mode auto @.session_prompt.md"
