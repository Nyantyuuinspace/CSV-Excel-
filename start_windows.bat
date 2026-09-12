@echo off
setlocal
cd /d "%~dp0" || goto fail
if not exist "%~dp0app.py" goto missing
where py >nul 2>nul
if not errorlevel 1 goto use_py
where python >nul 2>nul
if not errorlevel 1 goto use_python
echo Python 3 was not found. Install Python 3, then try again.
goto fail
:use_py
py -3 "%~dp0app.py"
goto done
:use_python
python "%~dp0app.py"
:done
if errorlevel 1 goto fail
exit /b 0
:missing
echo app.py is missing. Extract the whole ZIP before running this file.
:fail
echo Launch failed. Read the message above.
pause
exit /b 1
