@echo off
cd /d E:\options_scanner
python agents/system_analyst/launcher.py --prepare-only
wt -w 0 new-tab --title "System Analyst" cmd /k "cd /d E:\options_scanner\agents\system_analyst && claude --permission-mode auto @.session_prompt.md"
