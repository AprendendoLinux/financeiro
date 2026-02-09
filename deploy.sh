#!/bin/bash

# Cores para facilitar a leitura
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # Sem cor

echo -e "${YELLOW}--- Iniciando Processo de Deploy (Dev -> Main) ---${NC}"

# 1. Verifica se há arquivos não commitados
if [[ $(git status --porcelain) ]]; then
    echo -e "${RED}ERRO: Você tem alterações não salvas (uncommitted changes).${NC}"
    echo "Por favor, faça commit ou stash das suas alterações na dev antes de rodar o script."
    exit 1
fi

# 2. Garante que está na branch dev para pegar as últimas novidades
echo -e "${GREEN}1. Garantindo que estamos na branch dev...${NC}"
git checkout dev
git pull origin dev

# 3. Muda para main e atualiza
echo -e "${GREEN}2. Atualizando a branch main...${NC}"
git checkout main
git pull origin main

# 4. Faz o Merge da dev na main
echo -e "${GREEN}3. Fazendo merge da dev na main...${NC}"
if git merge dev; then
    echo -e "Merge realizado com sucesso."
else
    echo -e "${RED}ERRO: Conflito no merge. Resolva manualmente e tente novamente.${NC}"
    exit 1
fi

# 5. Pergunta a versão
echo -e "${YELLOW}---------------------------------------------------${NC}"
echo -e "${YELLOW}Qual será o número da nova versão? (ex: 1.0.5)${NC}"
read -p "Versão: " version_input

# Garante que começa com 'v'
if [[ $version_input != v* ]]; then
    version="v$version_input"
else
    version=$version_input
fi

echo -e "Você está prestes a lançar a versão: ${GREEN}$version${NC}"
read -p "Pressione [Enter] para confirmar ou [Ctrl+C] para cancelar..."

# 6. Envia a Main (Gera a imagem 'latest')
echo -e "${GREEN}4. Enviando atualizações para a Main...${NC}"
git push origin main

# 7. Cria e envia a Tag (Gera a imagem com versão fixa)
echo -e "${GREEN}5. Criando e enviando a Tag $version...${NC}"
git tag -a "$version" -m "Release $version"
git push origin "$version"

# 8. Volta para a dev
echo -e "${GREEN}6. Voltando para a branch dev...${NC}"
git checkout dev

echo -e "${YELLOW}--- SUCESSO! Deploy finalizado. ---${NC}"
echo -e "O GitHub Actions já deve estar construindo as imagens 'latest' e '$version'."