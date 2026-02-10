# 💰 Sistema de Controle Financeiro Personalizado

Um sistema robusto e intuitivo de gestão financeira pessoal desenvolvido com **Python (Flask)**, focado no controle total de despesas, receitas, contas bancárias e cartões de crédito com suporte a parcelamentos e lançamentos fixos.

## 🚀 Funcionalidades Principais

### 🔐 Gestão de Acessos e Segurança

* **Autenticação Completa:** Fluxo de login, registro e logout seguro utilizando `Flask-Login`.
* **Verificação de E-mail:** Ativação de conta via link enviado por e-mail para garantir a validade dos usuários.
* **Recuperação de Senha:** Sistema de "esqueci minha senha" com tokens temporários.
* **Perfil do Usuário:** Edição de dados pessoais e upload de foto de perfil (avatar).

### 📊 Dashboard e Transações

* **Visão Mensal:** Navegação por meses para acompanhamento histórico e futuro.
* **Gestão de Lançamentos:** Registro de receitas, despesas (débito/dinheiro) e transferências entre contas.
* **Filtros e Ordenação:** Tabela de transações com ordenação dinâmica por data/horário.
* **Status de Agendamento:** Identificação visual de lançamentos pendentes ou realizados.

### 💳 Cartões de Crédito e Parcelamentos

* **Controle de Faturas:** Gestão automática baseada no dia de fechamento e vencimento.
* **Compras Parceladas:** Lançamento de compras com divisão automática de parcelas em meses futuros.
* **Antecipação:** Funcionalidade exclusiva para antecipar parcelas futuras para a fatura atual.
* **Monitoramento de Limite:** Visualização em tempo real do limite utilizado e disponível.

### 🔄 Itens Fixos e Automação

* **Regras de Repetição:** Cadastro de despesas e receitas que se repetem mensalmente.
* **Renovação Automática:** Inteligência para gerar novas parcelas de despesas fixas de cartão conforme o horizonte de segurança.
* **Ativação Manual:** Controle de itens fixos de conta bancária via interruptores (toggle).

---

## 🛠️ Tecnologias Utilizadas

### **Backend**

* **Linguagem:** Python 3.11.
* **Framework:** Flask 3.0.0.
* **ORM:** SQLAlchemy (Flask-SQLAlchemy) para abstração de banco de dados.
* **Migrações:** Flask-Migrate para versionamento do esquema do banco.
* **Servidor:** Gunicorn para ambiente de produção.

### **Frontend**

* **Estilização:** Tailwind CSS com tema Dark Mode personalizado.
* **Ícones:** Font Awesome 6.0.
* **Interatividade:** JavaScript puro para manipulação de modais, máscaras de moeda e ordenação.

### **Infraestrutura**

* **Containerização:** Docker e Docker Compose.
* **Banco de Dados:** MySQL 8.0 (com suporte a SQLite para desenvolvimento local).
* **E-mail:** Integração SMTP para envio de notificações.

---

## 📂 Estrutura do Projeto

```text
├── app/
│   ├── templates/          # Arquivos HTML (Jinja2)
│   ├── static/             # Arquivos estáticos (uploads, assets)
│   ├── auth_controller.py  # Rotas de autenticação e segurança
│   ├── finance_controller.py # Lógica do dashboard e transações
│   ├── settings_controller.py# Gestão de categorias, contas e perfil
│   ├── models.py           # Definição das tabelas do banco de dados (SQLAlchemy)
│   ├── transaction_service.py# Regras de negócio centralizadas
│   ├── email_utils.py      # Utilitários para envio de e-mail HTML
│   ├── config.py           # Configurações de ambiente
│   └── run.py              # Ponto de entrada da aplicação
├── Dockerfile              # Configuração da imagem Docker
├── docker-compose.yml      # Orquestração de serviços (App + DB)
├── entrypoint.sh           # Script de inicialização (Migrações + Gunicorn)
└── requirements.txt        # Dependências do Python

```

---

## 🔧 Como Executar

### **Via Docker (Recomendado)**

1. Certifique-se de ter o Docker e Docker Compose instalados.
2. Clone o repositório.
3. Configure as variáveis de ambiente no `docker-compose.yml` (especialmente as de SMTP).
4. Execute o comando:
```bash
docker compose up -d --build

```


5. O sistema estará disponível em `http://localhost:5000`.

### **Configurações Importantes**

* **Preload:** O sistema possui um script `preload.py` que aguarda a disponibilidade do banco de dados antes de iniciar o servidor Flask, evitando erros de conexão no startup.
* **Migrações:** As migrações são aplicadas automaticamente ao subir o container via `entrypoint.sh`.

---

## 🔒 Variáveis de Ambiente

O sistema utiliza as seguintes variáveis para configuração:

| Variável | Descrição |
| --- | --- |
| `SECRET_KEY` | Chave de segurança para sessões Flask. |
| `DB_HOST` | Endereço do banco de dados MySQL. |
| `DB_USER` | Usuário do banco de dados. |
| `DB_PASSWORD` | Senha do banco de dados. |
| `SMTP_HOST` | Host do servidor de e-mail (ex: smtp.gmail.com). |
| `SMTP_USER` | Seu e-mail para envio de notificações. |
| `SMTP_PASSWORD` | Senha de aplicativo do e-mail. |

---

## 📝 Licença

Este projeto é desenvolvido para fins educacionais e de controle pessoal. Sinta-se à vontade para contribuir!

---

**Desenvolvido por Henrique Fagundes**.
Teste de deploy
Novo teste de deploy