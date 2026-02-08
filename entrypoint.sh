#!/bin/sh
set -e

echo "Verificando disponibilidade do banco de dados..."
python preload.py

export FLASK_APP=run

echo "Iniciando servidor Gunicorn..."
exec gunicorn --bind 0.0.0.0:5000 --workers 4 --timeout 120 run:app