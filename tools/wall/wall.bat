@echo off
REM wall - CLI shim, sits beside push-to-github.bat and pull-to-local.bat
REM Usage:  wall run-once
REM         wall doctor
REM         wall classify --staged
REM         wall agents roster
python "%~dp0wall.py" --repo "%~dp0..\.." %*
