@echo off
REM Earnings Researcher -- Sunday Maintenance / Housekeeping Session
REM Scheduled via Windows Task Scheduler (Sundays). Task: "!Sunday Earnings Researcher".
REM
REM Workspace upkeep + self-calibration, NOT research (per agent CLAUDE.md):
REM   archive research_log into memory/archive/, promote recurring facts into
REM   memory/reference_company_cadence.md, prune notes_for_ben.md, rotate outbox/,
REM   update STATUS.md. The dispute list is suppressed this day
REM   (.session_mode=weekend) so the session can summarize without context bloat.
REM
REM Two-step launch:
REM   1. launcher.py injects date into PROMPT_SUNDAY.md -> .session_prompt.md (weekend mode)
REM   2. Claude Code launches as a tab in the existing Windows Terminal window

cd /d E:\options_scanner

REM Step 1: Prepare the session prompt (maintenance/weekend mode)
python agents\earnings_researcher\launcher.py --prepare-only --prompt PROMPT_SUNDAY.md

REM Step 2: Launch Claude Code as a tab in the existing Windows Terminal window.
REM wt tabs do NOT inherit this .bat's cwd, so the cd is folded into cmd /k.
wt -w 0 new-tab --title "Earnings Researcher (Sunday)" cmd /k "cd /d E:\options_scanner\agents\earnings_researcher && claude --permission-mode auto @.session_prompt.md"
