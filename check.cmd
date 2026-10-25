@echo off
cd /d "%~dp0"
python scripts\manage.py check
pause
