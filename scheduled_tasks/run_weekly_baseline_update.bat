@echo off
cd /d E:\options_scanner
echo %date% %time% - Starting baseline update
python -m strategies.flow_monitor.fm_baseline_generator --lookback 21 --log-level INFO
echo %date% %time% - Baseline update completed