@echo off
rem Gelistirme icin: hatalari konsolda gosterir. Once acik olan DosyaKit'i kapatin.
cd /d "%~dp0"
".venv\Scripts\python.exe" -X utf8 DosyaKit.pyw %*
pause
