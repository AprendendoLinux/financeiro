FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
# IMPORTANTE: Faz com que a pasta /app seja reconhecida como o pacote 'app'
ENV PYTHONPATH=/

WORKDIR /app

# Instala dependências do sistema
RUN apt-get update && apt-get install -y \
    gcc \
    default-libmysqlclient-dev \
    pkg-config \
    netcat-openbsd \
    && apt-get clean all \
    && rm -rf /var/lib/apt/lists/*

# Copia e instala requirements, depois deleta o arquivo da imagem
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && rm requirements.txt \
    && pip cache purge \
    && rm -rf /tmp/pip-*

# Copia o CONTEÚDO da pasta app local para a raiz /app do container
COPY app/ .

# Copia o entrypoint (que está fora da pasta app localmente)
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

EXPOSE 5000

ENTRYPOINT ["./entrypoint.sh"]