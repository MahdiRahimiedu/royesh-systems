@echo off
cd /d "%~dp0..\.."
python scripts\manage.py start --service personnel
if errorlevel 1 pause
