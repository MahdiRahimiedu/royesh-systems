@echo off
cd /d "%~dp0"
python scripts\manage.py setup
if errorlevel 1 pause
