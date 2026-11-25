@echo off
cd /d "%~dp0"
start "" http://127.0.0.1:8765
"C:\Users\PC\AppData\Local\Programs\Python\Python313\python.exe" -X utf8 -m carfinder.web
