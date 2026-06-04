@echo off
REM Submodule-aware auto-commit + push to GitHub (cloud backup).
REM Point Windows Task Scheduler at THIS file (suggested: every 2 hours).
REM The real work is in auto_push.ps1 (next to this file). Non-interactive.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0auto_push.ps1"
