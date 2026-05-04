@echo off
title Maccabi Haifa Transfer Monitor
echo Starting Maccabi Haifa Transfer Intelligence System...
echo Press Ctrl+C to stop.
echo.
cd /d "%~dp0"
python monitor.py
pause
