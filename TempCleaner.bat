@echo off
REM Avvio rapido con doppio clic. Usa la versione di Python installata.
cd /d "%~dp0"
python -m tempcleaner %*
echo.
pause
