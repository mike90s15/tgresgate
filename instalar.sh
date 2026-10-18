#!/usr/bin/env sh
# Instala o tgresgate num ambiente virtual (Linux, macOS ou Termux).
set -e
cd "$(dirname "$0")"

if [ -n "$PREFIX" ] && echo "$PREFIX" | grep -q com.termux; then
    echo ">> Termux detectado"
    pkg install -y python >/dev/null
fi

command -v python3 >/dev/null || { echo "Instale o Python 3.8+ primeiro."; exit 1; }

echo ">> Criando ambiente virtual em ./venv"
python3 -m venv venv
./venv/bin/pip install -q --upgrade pip
./venv/bin/pip install -q -r requirements.txt

echo
echo "Instalado! Próximos passos:"
echo "  ./venv/bin/python tgresgate.py configurar"
echo "  ./venv/bin/python tgresgate.py login"
echo "  ./venv/bin/python tgresgate.py backup"
