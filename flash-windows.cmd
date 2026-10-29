@echo off
cd /d "%~dp0"
py -3 flash.py --download --erase-android
pause
