from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, current_app, make_response
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from app import db
from app.models import User, Category, BankAccount
from app.email_utils import send_email
from datetime import date, datetime, timedelta
import re
import secrets
import pyotp
import qrcode
import io
import base64
from itsdangerous import URLSafeTimedSerializer

auth_bp = Blueprint('auth', __name__)

# --- AUXILIARES ---
def validate_password_complexity(password):
    if len(password) < 6: return False
    if not re.search(r'[A-Z]', password): return False
    if not re.search(r'\d', password): return False
    if not re.search(r'[\W_]', password): return False
    return True

def validate_email_format(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def get_base_url():
    return request.host_url.rstrip('/')

def get_totp_object(user, method=None):
    """
    Retorna o objeto TOTP configurado corretamente.
    Se 'method' for passado (durante setup), usa ele. 
    Se não, usa o método salvo no banco (login).
    """
    target_method = method if method else user.two_factor_method
    
    if target_method == 'email':
        # Intervalo de 3600 segundos (1 hora) para E-mail
        return pyotp.TOTP(user.two_factor_secret, interval=3600)
    else:
        # Padrão 30 segundos para App
        return pyotp.TOTP(user.two_factor_secret)

def send_2fa_email(user, method=None):
    """Envia o código TOTP por e-mail com validade estendida."""
    # Passamos o method explicitamente para garantir que use o intervalo de 1h
    # mesmo que o usuário ainda não tenha ativado (durante o setup)
    totp = get_totp_object(user, method)
    code = totp.now()
    
    # HTML Personalizado para destaque (Sem botão)
    html_body = f"""
    <div style="text-align: center; padding: 20px;">
        <p style="color: #64748b; font-size: 16px;">Seu código de verificação é:</p>
        <h1 style="color: #2563eb; font-size: 48px; letter-spacing: 5px; margin: 20px 0; font-family: monospace;">{code}</h1>
        <p style="color: #94a3b8; font-size: 14px;">Este código é válido por aproximadamente 1 hora.</p>
    </div>
    """
    
    send_email(
        to_email=user.email,
        subject="Seu Código de Acesso",
        title="Verificação de Segurança",
        body_content=html_body,
        action_url=None, 
        action_text=None
    )

def set_trusted_cookie(response, user_id):
    """Define o cookie de dispositivo confiável por 30 dias"""
    s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    token = s.dumps(user_id, salt='trusted-device')
    # Cookie dura 30 dias. 
    response.set_cookie('trusted_device', token, max_age=30*24*3600, httponly=True, secure=False)

def is_device_trusted(user_id):
    """Verifica se o cookie de dispositivo confiável é válido"""
    token = request.cookies.get('trusted_device')
    if not token:
        return False
    
    s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    try:
        # Valida o token (max_age garante os 30 dias)
        data = s.loads(token, salt='trusted-device', max_age=30*24*3600)
        return data == user_id
    except:
        return False

# --- ROTAS ---

@auth_bp.route('/', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('finance.dashboard'))
        
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        remember = True if request.form.get('remember') else False
        
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            # VERIFICAÇÃO DE 2FA
            if user.two_factor_method:
                # Se o dispositivo for confiável, pula o 2FA
                if is_device_trusted(user.id):
                    login_user(user, remember=remember)
                    return redirect(url_for('finance.dashboard'))

                session['2fa_user_id'] = user.id
                session['2fa_remember'] = remember
                
                if user.two_factor_method == 'email':
                    try:
                        # Aqui o método já está salvo, então não precisamos forçar
                        send_2fa_email(user)
                        flash('Código de verificação enviado para seu e-mail.', 'info')
                    except Exception as e:
                        print(f"Erro ao enviar 2FA email: {e}")
                        flash('Erro ao enviar e-mail. Tente novamente.', 'danger')

                return redirect(url_for('auth.verify_2fa_login'))

            # Login padrão (sem 2FA)
            login_user(user, remember=remember)
            return redirect(url_for('finance.dashboard'))
        else:
            flash('E-mail ou senha incorretos.', 'danger')
            
    return render_template('login.html')

@auth_bp.route('/login/2fa', methods=['GET', 'POST'])
def verify_2fa_login():
    if '2fa_user_id' not in session:
        return redirect(url_for('auth.login'))
    
    user = User.query.get(session['2fa_user_id'])
    if not user:
        session.pop('2fa_user_id', None)
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        code = request.form.get('code')
        trust_device = request.form.get('trust_device') # Checkbox
        
        if code: code = code.replace(" ", "")
        
        # Usa o objeto TOTP correto (1h se email, 30s se app)
        totp = get_totp_object(user)
        
        # valid_window=1 permite pequena tolerância de tempo
        if totp.verify(code, valid_window=1):
            remember = session.get('2fa_remember', False)
            session.pop('2fa_user_id', None)
            session.pop('2fa_remember', None)
            
            login_user(user, remember=remember)
            
            resp = make_response(redirect(url_for('finance.dashboard')))
            
            # Se marcou "Confiar neste dispositivo"
            if trust_device:
                set_trusted_cookie(resp, user.id)
                
            return resp
        else:
            flash('Código inválido ou expirado.', 'danger')
            
    return render_template('verify_2fa.html', method=user.two_factor_method)

@auth_bp.route('/login/2fa/resend')
def resend_2fa_code():
    if '2fa_user_id' not in session:
        return redirect(url_for('auth.login'))
    
    user = User.query.get(session['2fa_user_id'])
    if user and user.two_factor_method == 'email':
        try:
            send_2fa_email(user)
            flash('Código reenviado com sucesso!', 'success')
        except Exception as e:
            print(f"Erro reenvio: {e}")
            flash('Erro ao enviar e-mail.', 'danger')
    
    return redirect(url_for('auth.verify_2fa_login'))

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('finance.dashboard'))
        
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if password != confirm_password:
            flash('As senhas não conferem.', 'warning')
            return redirect(url_for('auth.register'))
            
        if not validate_password_complexity(password):
            flash('A senha deve ter no mínimo 6 caracteres, conter letras maiúsculas, números e símbolos.', 'warning')
            return redirect(url_for('auth.register'))
            
        if User.query.filter_by(email=email).first():
            flash('Este e-mail já está cadastrado.', 'danger')
            return redirect(url_for('auth.register'))
            
        new_user = User(name=name, email=email)
        new_user.set_password(password)
        new_user.start_date = date.today().replace(day=1)
        
        db.session.add(new_user)
        db.session.commit()
        
        # Cria contas e categorias padrão
        default_account = BankAccount(user_id=new_user.id, name='Carteira de dinheiro', current_balance=0.0)
        db.session.add(default_account)
        
        default_cats = [
            ('Salário', 'receita', '#10b981'), ('Investimentos', 'receita', '#10b981'), 
            ('Extras', 'receita', '#10b981'),
            ('Moradia', 'despesa', '#ef4444'), ('Alimentação', 'despesa', '#ef4444'), 
            ('Transporte', 'despesa', '#ef4444'), ('Saúde', 'despesa', '#ef4444'),
            ('Educação', 'despesa', '#ef4444'), ('Lazer', 'despesa', '#ef4444'),
            ('Compras', 'despesa', '#ef4444'),
            ('Transferência', 'transferencia', '#3B82F6'),
            ('Pagamento', 'pagamento', '#EF4444')
        ]
        for cn, ct, cc in default_cats:
            db.session.add(Category(user_id=new_user.id, name=cn, type=ct, color_hex=cc))
            
        db.session.commit()
        
        flash('Cadastro realizado com sucesso! Faça login.', 'success')
        return redirect(url_for('auth.login'))
        
    return render_template('register.html')

@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        user = User.query.filter_by(email=email).first()
        
        if user:
            token = secrets.token_urlsafe(32)
            user.auth_token = token
            user.token_expiration = datetime.utcnow() + timedelta(hours=1)
            db.session.commit()
            
            link = f"{get_base_url()}/reset-password/{token}"
            
            try:
                send_email(
                    to_email=user.email,
                    subject="Recuperação de Senha",
                    title="Recuperar Senha",
                    body_content=f"Olá {user.name}. Recebemos um pedido para redefinir sua senha. Se não foi você, ignore este e-mail.",
                    action_url=link,
                    action_text="Redefinir Senha"
                )
            except Exception as e:
                print(f"Erro ao enviar email: {e}")
        
        flash('Se o e-mail existir, as instruções foram enviadas.', 'info')
        return redirect(url_for('auth.login'))
        
    return render_template('forgot_password.html')

@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    user = User.query.filter_by(auth_token=token).first()
    
    if not user or user.token_expiration < datetime.utcnow():
        flash('Link inválido ou expirado.', 'danger')
        return redirect(url_for('auth.login'))
        
    if request.method == 'POST':
        password = request.form.get('password')
        confirm = request.form.get('confirm_password')
        
        if password != confirm:
            flash('As senhas não conferem.', 'warning')
            return redirect(request.url)
            
        if not validate_password_complexity(password):
            flash('A senha não atende aos requisitos.', 'warning')
            return redirect(request.url)
            
        user.set_password(password)
        user.auth_token = None
        user.token_expiration = None
        user.is_verified = True
        db.session.commit()
        
        flash('Senha alterada com sucesso!', 'success')
        return redirect(url_for('auth.login'))
        
    return render_template('reset_password.html')

# --- ROTAS DE CONFIGURAÇÃO DO 2FA ---

@auth_bp.route('/settings/2fa/setup', methods=['POST'])
@login_required
def setup_2fa():
    method = request.form.get('method')
    
    # Se já existir segredo, reutiliza. Senão, cria novo.
    if not current_user.two_factor_secret:
        current_user.two_factor_secret = pyotp.random_base32()
        db.session.commit()
    
    resp = {
        'status': 'ok',
        'method': method,
        'secret': current_user.two_factor_secret
    }
    
    if method == 'app':
        # Gera QR Code (Padrão 30s)
        # Nota: Provisioning URI usa o padrão (30s) para apps autenticadores.
        totp = pyotp.TOTP(current_user.two_factor_secret)
        uri = totp.provisioning_uri(name=current_user.email, issuer_name='Financeiro App')
        
        img = qrcode.make(uri)
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()
        resp['qr_code'] = f"data:image/png;base64,{img_str}"
        
    elif method == 'email':
        # Envia email (forçando intervalo de 1h)
        try:
            send_2fa_email(current_user, method='email')
        except Exception as e:
            print(f"Erro ao enviar email de setup: {e}")
            return jsonify({'status': 'error', 'message': 'Erro ao enviar e-mail.'}), 500
        
    return jsonify(resp)

@auth_bp.route('/settings/2fa/enable', methods=['POST'])
@login_required
def enable_2fa():
    code = request.form.get('code')
    method = request.form.get('method')
    trust_device = request.form.get('trust_device') # Checkbox na ativação
    
    if code: code = code.replace(" ", "")
    
    # Validação inicial usa a lógica específica do método escolhido
    if method == 'email':
        totp = pyotp.TOTP(current_user.two_factor_secret, interval=3600)
    else:
        totp = pyotp.TOTP(current_user.two_factor_secret)
    
    if totp.verify(code, valid_window=1):
        current_user.two_factor_method = method
        db.session.commit()
        
        flash(f'Autenticação de Dois Fatores ({method.upper()}) ativada com sucesso!', 'success')
        
        resp = make_response(redirect(url_for('settings.index', tab='account')))
        
        # Opção de confiar já na ativação
        if trust_device:
            set_trusted_cookie(resp, current_user.id)
            
        return resp
    else:
        flash('Código incorreto. A ativação falhou.', 'danger')
        return redirect(url_for('settings.index', tab='account'))

@auth_bp.route('/settings/2fa/disable', methods=['POST'])
@login_required
def disable_2fa():
    current_user.two_factor_method = None
    current_user.two_factor_secret = None
    db.session.commit()
    
    # Remove cookie de confiança também
    resp = make_response(redirect(url_for('settings.index', tab='account')))
    resp.set_cookie('trusted_device', '', expires=0)
    
    flash('Autenticação de Dois Fatores desativada.', 'warning')
    return resp

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Você saiu do sistema.', 'info')
    return redirect(url_for('auth.login'))