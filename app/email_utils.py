import smtplib
import ssl
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

def _get_html_template(title: str, body_content: str, action_url: str = None, action_text: str = None):
    """Template HTML limpo e responsivo para o Sistema Financeiro."""
    
    button_html = ""
    if action_url and action_text:
        button_html = f"""
        <table role="presentation" border="0" cellpadding="0" cellspacing="0" class="btn btn-primary" style="margin: 20px auto;">
            <tbody>
            <tr>
                <td align="center">
                    <a href="{action_url}" target="_blank" style="background-color: #2563EB; border-radius: 8px; color: #ffffff; display: inline-block; padding: 12px 24px; text-decoration: none; font-weight: bold; font-size: 16px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">{action_text}</a>
                </td>
            </tr>
            </tbody>
        </table>
        """

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta name="viewport" content="width=device-width" />
        <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
        <title>{title}</title>
        <style>
            body {{ background-color: #f1f5f9; font-family: sans-serif; -webkit-font-smoothing: antialiased; font-size: 14px; line-height: 1.4; margin: 0; padding: 0; -ms-text-size-adjust: 100%; -webkit-text-size-adjust: 100%; }}
            .body {{ background-color: #f1f5f9; width: 100%; }}
            .container {{ display: block; margin: 0 auto !important; max-width: 580px; padding: 10px; width: 580px; }}
            .content {{ box-sizing: border-box; display: block; margin: 0 auto; max-width: 580px; padding: 10px; }}
            .main {{ background: #ffffff; border-radius: 8px; width: 100%; border: 1px solid #e2e8f0; }}
            .wrapper {{ box-sizing: border-box; padding: 20px; }}
            h1 {{ font-size: 24px; font-weight: bold; margin: 0 0 15px; text-align: center; color: #1e293b; }}
            p {{ font-size: 15px; font-weight: normal; margin: 0 0 15px; color: #475569; }}
            .footer {{ clear: both; margin-top: 10px; text-align: center; width: 100%; }}
            .footer td, .footer p, .footer span, .footer a {{ color: #94a3b8; font-size: 12px; text-align: center; }}
        </style>
    </head>
    <body class="">
        <table role="presentation" border="0" cellpadding="0" cellspacing="0" class="body">
            <tr>
                <td>&nbsp;</td>
                <td class="container">
                    <div class="content">
                        <table role="presentation" class="main">
                            <tr>
                                <td class="wrapper">
                                    <table role="presentation" border="0" cellpadding="0" cellspacing="0">
                                        <tr>
                                            <td>
                                                <div style="text-align: center; margin-bottom: 20px;">
                                                    <span style="font-size: 24px; color: #2563EB; font-weight: bold;">Financeiro</span>
                                                </div>
                                                <h1>{title}</h1>
                                                <p>{body_content}</p>
                                                {button_html}
                                                <p>Se você não solicitou esta ação, por favor ignore este e-mail.</p>
                                            </td>
                                        </tr>
                                    </table>
                                </td>
                            </tr>
                        </table>
                        <div class="footer">
                            <table role="presentation" border="0" cellpadding="0" cellspacing="0">
                                <tr>
                                    <td class="content-block">
                                        <span>© 2026 Sistema de Controle Financeiro</span>
                                    </td>
                                </tr>
                            </table>
                        </div>
                    </div>
                </td>
                <td>&nbsp;</td>
            </tr>
        </table>
    </body>
    </html>
    """

def send_email(to_email: str, subject: str, title: str, body_content: str, action_url: str = None, action_text: str = None):
    """Envia um e-mail HTML usando SMTP."""
    
    # Alteração: Removemos a obrigatoriedade de SMTP_USER aqui
    if not SMTP_HOST:
        logger.error("Configurações de SMTP (Host) não encontradas. O e-mail não será enviado.")
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM
    msg["To"] = to_email

    html_content = _get_html_template(title, body_content, action_url, action_text)
    msg.set_content("Por favor habilite HTML para ver este e-mail.") # Fallback
    msg.add_alternative(html_content, subtype="html")

    try:
        logger.info(f"Conectando ao SMTP {SMTP_HOST}:{SMTP_PORT}...")
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
        
        # Modo Debug se necessário
        # server.set_debuglevel(1)

        server.ehlo()
        # Geralmente portas 587 usam STARTTLS, porta 25 interna não
        if SMTP_PORT == 587:
            server.starttls()
            server.ehlo()

        # Alteração: Login apenas se as credenciais existirem
        if SMTP_USER and SMTP_PASSWORD:
            server.login(SMTP_USER, SMTP_PASSWORD)
            
        server.send_message(msg)
        server.quit()
        
        logger.info(f"E-mail enviado para {to_email}")
        return True
    except Exception as e:
        logger.error(f"Erro ao enviar e-mail: {e}")
        return False