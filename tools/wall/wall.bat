@echo off
REM wall - CLI shim, sits beside push-to-github.bat and pull-to-local.bat
REM Usage:  wall run-once
REM         wall doctor
REM         wall classify --staged
REM         wall agents roster
REM         wall agents whois --name Desmond --at 2026-09-22T12:00:00Z
REM         wall compliance-scan
python "%~dp0wall.py" --repo "%~dp0..\.." %*
