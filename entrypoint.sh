#!/bin/sh
set -e

echo "Verificando disponibilidade do banco de dados..."
python preload.py

export FLASK_APP=run

echo "Iniciando servidor Gunicorn (IPv4 + IPv6)..."
# Usar apenas [::]:5000 habilita Dual-Stack (IPv4 e IPv6) automaticamente no Linux
exec gunicorn --bind "[::]:5000" --workers 4 --timeout 120 run:app