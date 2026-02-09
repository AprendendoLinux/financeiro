import smtplib
import os
import logging
from email.message import EmailMessage

# --- CONFIGURAÇÃO DE LOGS ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("email_utils")

# Configurações de SMTP (Environment Variables)
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587)) 
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_FROM = os.getenv("SMTP_FROM", "Financeiro <noreply@financeiro.com>")

def send_email(to_email: str, subject: str, html_content: str):
    """
    Envia um e-mail HTML usando SMTP.
    Agora recebe o HTML pronto renderizado pelo Jinja2.
    """
    
    if not SMTP_HOST:
        logger.error("Configurações de SMTP (Host) não encontradas. O e-mail não será enviado.")
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM
    msg["To"] = to_email

    # Define o conteúdo HTML
    msg.set_content("Por favor habilite HTML para ver este e-mail.") # Fallback texto puro
    msg.add_alternative(html_content, subtype="html")

    try:
        logger.info(f"Conectando ao SMTP {SMTP_HOST}:{SMTP_PORT} para enviar a {to_email}...")
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
        
        server.ehlo()
        if SMTP_PORT == 587:
            server.starttls()
            server.ehlo()

        if SMTP_USER and SMTP_PASSWORD:
            server.login(SMTP_USER, SMTP_PASSWORD)
            
        server.send_message(msg)
        server.quit()
        logger.info("E-mail enviado com sucesso!")
        return True

    except Exception as e:
        logger.error(f"Falha ao enviar e-mail: {e}")
        return False