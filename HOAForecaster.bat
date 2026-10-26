@echo off
rem HOAForecaster - double-click launcher.
rem
rem Runs exactly what "uv run hoaforecaster" runs: the local server on 127.0.0.1, with your
rem projects in the data folder (HOA_DATA_DIR if set, else %APPDATA%\HOAForecaster). The
rem server opens the app in your browser itself, once it is listening - it waits for its
rem own server, so a tab never opens onto another program that happens to hold the port.
rem
rem This file adds the things a double-click needs and a terminal does not.
rem
rem   * It sets its own working directory. Explorer can start a script from anywhere, and
rem     uv finds the project from the working directory.
rem   * It checks that uv is installed, and says how to get it, rather than failing with
rem     "'uv' is not recognized".
rem   * It pauses at the end when something failed. Without that, the window vanishes the
rem     moment something fails - a first build that cannot find npm, the port already in
rem     use - and takes the message with it, which reads as "nothing happened".
rem
rem The first start takes a minute or two: uv installs the Python packages and the screens
rem are built with npm. Later starts are quick.
rem
rem Stop the app with Ctrl+C in this window, or just close the window. Double-clicking this file
rem while the app is running stops the running copy cleanly first, and that copy's window
rem closes by itself.

setlocal
cd /d "%~dp0"
title HOAForecaster

where uv >nul 2>nul
if errorlevel 1 (
    echo HOAForecaster needs uv, which is not installed or not on the PATH.
    echo Install it from https://docs.astral.sh/uv/ and double-click this file again.
    echo.
    pause
    exit /b 1
)

echo Starting HOAForecaster...
echo A browser tab opens by itself once the server is listening. Ctrl+C stops it.
echo.

uv run hoaforecaster %*
set code=%errorlevel%

echo.
echo HOAForecaster has stopped.
rem keep the message on screen only when something went wrong
if not "%code%"=="0" pause
endlocal
