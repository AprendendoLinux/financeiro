#!/bin/sh
set -e

# --- NOVO BLOCO DE PRELOAD ---
# Executa o script Python que está na mesma pasta (WORKDIR)
# Ele vai travar a execução aqui até o banco responder ou dar timeout
echo "Verificando disponibilidade do banco de dados..."
python preload.py
# -----------------------------

export FLASK_APP=run

# Verifica se precisa inicializar o migrations
if [ ! -f "migrations/env.py" ]; then
    echo "Diretório de migrações vazio ou inexistente. Inicializando..."
    flask db init
fi

# Migração (Idealmente manual, mas mantido conforme seu fluxo dev)
echo "Gerando migrações automáticas (Dev Mode)..."
flask db migrate -m "Auto migration startup" || true

echo "Aplicando migrações..."
flask db upgrade

echo "Iniciando servidor Gunicorn..."
# Bind no 0.0.0.0 é essencial para acesso externo ao container
exec gunicorn --bind 0.0.0.0:5000 --workers 4 --timeout 120 run:app