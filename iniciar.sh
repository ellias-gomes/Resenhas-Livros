#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

IP_REDE=$(python3 -c 'import socket; s=socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(("8.8.8.8",80)); print(s.getsockname()[0]); s.close()' 2>/dev/null || hostname -I | awk '{print $1}')

echo "============================================================"
echo " 💜 Entrelinhas & Telas — Rede Social Doméstica de Resenhas"
echo "============================================================"
echo " 🖥️  Neste computador: http://localhost:8000"
echo " 📱 Na rede Wi-Fi:    http://${IP_REDE}:8000"
echo "============================================================"

exec ./venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 --reload
