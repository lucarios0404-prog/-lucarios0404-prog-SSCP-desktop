@echo off
title Compilando SSCP Desktop (.exe)
echo ========================================================
echo   Iniciando compilacion de SSCP Desktop con PyInstaller
echo ========================================================
echo.
call venv\Scripts\activate.bat
python build_exe.py
echo.
pause
