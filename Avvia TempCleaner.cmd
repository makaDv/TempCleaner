@echo off
setlocal EnableExtensions
title TempCleaner
cd /d "%~dp0"

rem TempCleaner - avvio con doppio clic.
rem Usa Python, firmato dalla Python Software Foundation: nessun .exe da sbloccare.
rem Se Python manca, propone di installarlo con winget (strumento ufficiale Microsoft).

set "TEMPCLEANER_LAUNCHER=1"
set "PY="
call :find_python
if not defined PY call :offer_install
if not defined PY goto :no_python

if exist "%~dp0TempCleaner-app.pyz" (
    "%PY%" "%~dp0TempCleaner-app.pyz" %*
) else (
    "%PY%" -m tempcleaner %*
)
exit /b %errorlevel%


:find_python
call :try_python py -3
if not defined PY call :try_python python
if not defined PY for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*" "%ProgramFiles%\Python3*" "%SystemDrive%\Python3*") do (
    if not defined PY if exist "%%~D\python.exe" call :try_python "%%~D\python.exe"
)
goto :eof

:try_python
rem Accetta solo Python 3.9 o superiore e ricava il percorso reale di python.exe.
for /f "usebackq delims=" %%P in (`call %* -c "import sys; print(sys.executable if sys.version_info >= (3, 9) else '')" 2^>nul`) do set "PY=%%P"
goto :eof

:offer_install
echo.
echo  TempCleaner ha bisogno di Python 3.9 o superiore, che non risulta installato.
where winget >nul 2>nul || goto :eof
echo  Puo' essere installato ora con winget, lo strumento ufficiale di Microsoft.
echo.
choice /c SN /n /m " Installare Python 3.12 adesso? [S/N] "
if errorlevel 2 goto :eof
winget install --exact --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
call :find_python
goto :eof

:no_python
echo.
echo  Python non disponibile.
echo  Scaricalo da https://www.python.org/downloads/ ^(spunta "Add python.exe to PATH"^),
echo  poi apri di nuovo "Avvia TempCleaner.cmd".
echo.
pause
exit /b 1
