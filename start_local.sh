#!/usr/bin/env bash
set -e
python3 -m venv .venv || true
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
if [ ! -f .env ]; then
  echo "Create .env from .env.example and fill tokens/URL."
  exit 1
fi
python server.py
