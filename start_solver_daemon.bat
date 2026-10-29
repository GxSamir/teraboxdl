@echo off
cd /d "%~dp0"
echo ============================================================
echo   TeraBoxDL Turnstile Auto-Sync Daemon
echo ============================================================
echo Starting background solver daemon for https://tbf-dl.teraboxfast.com...
wscript "%~dp0run_solver_background.vbs"
echo.
echo [+] Turnstile solver is now running silently in the background!
echo [+] It will refresh the VPS token every 5 minutes.
echo ============================================================
timeout /t 5
