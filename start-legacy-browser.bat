@echo off
call venv\Scripts\activate.bat
start http://localhost:8080
uvicorn main:app --host 0.0.0.0 --port 8080 --reload
