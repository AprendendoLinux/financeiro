import time
import sys
from sqlalchemy import text
from app import create_app, db

def wait_for_db():
    """
    Aguarda o banco de dados estar disponível silenciosamente.
    Erro técnico só é exibido em caso de timeout total.
    """
    print("--- PRELOAD: Aguardando disponibilidade do Banco de Dados... ---")
    
    flask_app = create_app()
    
    # Configurações
    max_retries = 60
    interval = 2
    last_error = None

    with flask_app.app_context():
        for i in range(max_retries):
            try:
                # Tenta conexão
                db.session.execute(text('SELECT 1'))
                print("--- PRELOAD: Conexão estabelecida com sucesso! ---")
                return True
                
            except Exception as e:
                # Guarda o erro para mostrar apenas se falhar tudo
                last_error = e
                # Imprime apenas um ponto ou mensagem curta para indicar vida, sem poluir
                # O 'flush=True' garante que o print apareça na hora no log do Docker
                print(f"--- Aguardando banco... ({i+1}/{max_retries})", flush=True)
                time.sleep(interval)
        
        # Se saiu do loop, é porque estourou o tempo
        print("\n" + "="*50)
        print("FALHA CRÍTICA NO PRELOAD")
        print("="*50)
        print("Não foi possível conectar ao banco após todas as tentativas.")
        print(f"Último erro capturado: {last_error}")
        print("="*50 + "\n")
        sys.exit(1)

if __name__ == "__main__":
    wait_for_db()