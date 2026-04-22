@echo off
cd /d E:\options_scanner
python agents/system_analyst/launcher.py --prepare-only --prompt agents/system_analyst/PROMPT_SUNDAY.md
wt -w 0 new-tab --title "System Analyst (Sunday)" cmd /k "cd /d E:\options_scanner && claude --permission-mode bypassPermissions @agents/system_analyst/.session_prompt.md"
