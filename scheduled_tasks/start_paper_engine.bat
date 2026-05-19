@echo off
REM Paper Close Engine — Phase B
REM Schedule this every 2 minutes during market hours (M-F 9:30 AM - 4:00 PM ET).
REM The engine self-skips price-based evaluation when the Tradier clock reports closed.
REM Add --dry-run to the command below for the initial deployment day (safety net).
cd /d E:\options_scanner && python tools/paper_close_engine.py
