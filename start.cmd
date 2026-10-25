@echo off
cd /d "%~dp0"
python scripts\manage.py start
if errorlevel 1 pause
