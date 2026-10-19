' Simple Mode launcher (PRD 0014): runs the daily cycle headless.
'
' Starts "python main.py --simple-mode" with its console hidden. Output still
' goes to the usual files in logs/ (orchestrator_*.log, flow_monitor_*.log).
' Autofix fix sessions still open visibly (verified 2026-10-19).
'
' Task Scheduler (\!main.py):  wscript.exe "E:\options_scanner\scheduled_tasks\start_main_simple.vbs"
' Full system instead:          point the task back at start_main.bat
' Manual / Autofix restart:     wscript scheduled_tasks\start_main_simple.vbs

Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(fso.GetParentFolderName(WScript.ScriptFullName))
CreateObject("WScript.Shell").Run "cmd /c cd /d """ & root & """ && python main.py --simple-mode", 0, False
