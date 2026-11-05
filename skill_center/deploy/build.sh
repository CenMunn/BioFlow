#!/usr/bin/env bash
set -euo pipefail
umask 077
cd "$(dirname "$0")/.."
export PATH="/home/xh/.nvm/versions/node/v22.23.2/bin:$PATH"
test -x .venv/bin/python || python3 -m venv .venv
if [ -f requirements.lock ] && [ "${SC_UPDATE_BACKEND_LOCK:-0}" != 1 ]; then
  .venv/bin/python -m pip install --disable-pip-version-check -r requirements.lock
else
  .venv/bin/python -m pip install --disable-pip-version-check -r requirements.txt
fi
.venv/bin/python -m pip freeze > requirements.lock
cd frontend
if [ "${SC_UPDATE_LOCK:-0}" = 1 ] || [ ! -f package-lock.json ]; then npm install --no-audit --no-fund; else npm ci --no-audit --no-fund; fi
npm run format
npm run build
cd ..
.venv/bin/python -m pytest tests -q
echo 'BUILD_AND_TEST_OK'
