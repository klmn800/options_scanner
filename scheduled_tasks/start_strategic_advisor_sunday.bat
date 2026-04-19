@echo off
cd /d E:\options_scanner
python strategic_advisor/launcher.py --prepare-only --prompt strategic_advisor/PROMPT_SUNDAY.md
wt -w 0 new-tab --title "Strategic Advisor (Sunday)" cmd /k "cd /d E:\options_scanner && claude --permission-mode bypassPermissions @strategic_advisor\.session_prompt.md"
