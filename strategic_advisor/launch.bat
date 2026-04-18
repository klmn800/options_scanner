@echo off
cd /d E:\options_scanner
echo ================================================
echo  Strategic Advisor — Session Launch
echo ================================================
echo.
echo Starting Claude Code with Strategic Advisor prompt...
echo.
start "" cmd /k "cd /d E:\options_scanner && claude --permission-mode bypassPermissions @strategic_advisor\PROMPT.md"
