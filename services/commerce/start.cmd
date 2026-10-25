@echo off
cd /d "%~dp0..\.."
python scripts\manage.py start --service commerce
if errorlevel 1 pause
