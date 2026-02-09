import time
import sys
from sqlalchemy import text, inspect
from app import create_app, db

def wait_for_db():
    """
    Aguarda o banco de dados estar disponível e garante a criação das tabelas.
    """
    print("--- PRELOAD: Aguardando disponibilidade do Banco de Dados... ---")
    
    flask_app = create_app()
    
    # Configurações
    max_retries = 60
    interval = 2
    last_error = None

    with flask_app.app_context():
        # 1. Aguarda Conexão
        connected = False
        for i in range(max_retries):
            try:
                # Tenta conexão
                db.session.execute(text('SELECT 1'))
                print("--- PRELOAD: Conexão estabelecida com sucesso! ---")
                connected = True
                break
                
            except Exception as e:
                # Guarda o erro para mostrar apenas se falhar tudo
                last_error = e
                # Imprime apenas um ponto ou mensagem curta para indicar vida, sem poluir
                print(f"--- Aguardando banco... ({i+1}/{max_retries})", flush=True)
                time.sleep(interval)
        
        if not connected:
            # Se saiu do loop, é porque estourou o tempo
            print("\n" + "="*50)
            print("FALHA CRÍTICA NO PRELOAD")
            print("="*50)
            print("Não foi possível conectar ao banco após todas as tentativas.")
            print(f"Último erro capturado: {last_error}")
            print("="*50 + "\n")
            sys.exit(1)

        # 2. Verifica e Cria Tabelas (Se necessário)
        try:
            inspector = inspect(db.engine)
            # Se a tabela 'users' não existir, roda o create_all
            if not inspector.has_table("users"):
                print("--- PRELOAD: Tabelas não encontradas. Criando estrutura do banco... ---")
                db.create_all()
                print("--- PRELOAD: Tabelas criadas com sucesso! ---")
            else:
                print("--- PRELOAD: Tabelas já existem. ---")
                
        except Exception as e:
            print(f"--- ERRO AO CRIAR TABELAS: {e} ---")
            # Não aborta para tentar subir mesmo assim, mas avisa no log
            pass

if __name__ == "__main__":
    wait_for_db()