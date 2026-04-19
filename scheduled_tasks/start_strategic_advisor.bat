@echo off
cd /d E:\options_scanner
python strategic_advisor/launcher.py --prepare-only
start "Strategic Advisor" cmd /k "cd /d E:\options_scanner && claude --permission-mode bypassPermissions @strategic_advisor\.session_prompt.md"
