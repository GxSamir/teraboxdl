@echo off
cd /d "%~dp0"
echo ============================================================
echo   TeraBoxDL - Install Windows Auto-Start Task
echo ============================================================
echo Registering task "TeraBoxDLTurnstileSync" in Windows Task Scheduler...
schtasks /create /tn "TeraBoxDLTurnstileSync" /tr "wscript.exe \"%~dp0run_solver_background.vbs\"" /sc onlogon /f
if %ERRORLEVEL% equ 0 (
    echo.
    echo [+] Successfully installed!
    echo [+] The solver daemon will now automatically run silently in the background
    echo     whenever you turn on or log in to your computer.
) else (
    echo.
    echo [!] Could not register task automatically. Please right-click and 'Run as Administrator'.
)
echo ============================================================
pause
