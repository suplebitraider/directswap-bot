@echo off
setlocal
if not exist .venv (
  py -m venv .venv
)
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
if not exist .env (
  echo Create .env from .env.example and fill tokens/URL.
  pause
  exit /b 1
)
python server.py
