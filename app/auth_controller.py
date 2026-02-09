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
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadTimeSignature

auth_bp = Blueprint('auth', __name__)

# --- AUXILIARES (Mantidos iguais) ---
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

def generate_confirmation_token(email):
    serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    return serializer.dumps(email, salt='email-confirm-salt')

def confirm_token(token, expiration=3600):
    serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    try:
        email = serializer.loads(token, salt='email-confirm-salt', max_age=expiration)
    except (SignatureExpired, BadTimeSignature):
        return False
    return email

def get_totp_object(user, method=None):
    target_method = method if method else user.two_factor_method
    if target_method == 'email':
        return pyotp.TOTP(user.two_factor_secret, interval=3600)
    else:
        return pyotp.TOTP(user.two_factor_secret)

def send_2fa_email(user, method=None):
    totp = get_totp_object(user, method)
    code = totp.now()
    
    # Renderiza o template bonito do 2FA
    html_content = render_template(
        'email/two_factor.html',
        user=user,
        code=code,
        current_year=datetime.now().year
    )
    
    send_email(
        to_email=user.email,
        subject="Seu Código de Acesso",
        html_content=html_content
    )

def set_trusted_cookie(response, user_id):
    s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    token = s.dumps(user_id, salt='trusted-device')
    response.set_cookie('trusted_device', token, max_age=30*24*3600, httponly=True, secure=False)

def is_device_trusted(user_id):
    token = request.cookies.get('trusted_device')
    if not token:
        return False
    
    s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    try:
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
            if not user.is_verified:
                flash('Por favor, confirme seu e-mail antes de fazer login.', 'warning')
                return redirect(url_for('auth.login'))

            if user.two_factor_method:
                if is_device_trusted(user.id):
                    login_user(user, remember=remember)
                    return redirect(url_for('finance.dashboard'))

                session['2fa_user_id'] = user.id
                session['2fa_remember'] = remember
                
                if user.two_factor_method == 'email':
                    try:
                        send_2fa_email(user)
                        flash('Código de verificação enviado para seu e-mail.', 'info')
                    except Exception as e:
                        print(f"Erro ao enviar 2FA email: {e}")
                        flash('Erro ao enviar e-mail. Tente novamente.', 'danger')

                return redirect(url_for('auth.verify_2fa_login'))

            login_user(user, remember=remember)
            
            if not user.two_factor_method:
                flash('Recomendamos ativar a autenticação de dois fatores.', 'setup_2fa')
                
            return redirect(url_for('finance.dashboard'))
        else:
            flash('E-mail ou senha incorretos.', 'danger')
            
    return render_template('login.html')

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        logout_user()
        
    if request.method == 'POST':
        name = request.form.get('name')
        last_name = request.form.get('last_name')
        email = request.form.get('email')
        birth_date_str = request.form.get('birth_date')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        birth_date = None
        if birth_date_str:
            try:
                birth_date = datetime.strptime(birth_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass

        if password != confirm_password:
            flash('As senhas não conferem.', 'warning')
            return redirect(url_for('auth.register'))
            
        if not validate_password_complexity(password):
            flash('A senha deve ter no mínimo 6 caracteres...', 'warning')
            return redirect(url_for('auth.register'))
            
        if User.query.filter_by(email=email).first():
            flash('Este e-mail já está cadastrado.', 'danger')
            return redirect(url_for('auth.register'))
            
        new_user = User(
            name=name,
            last_name=last_name,
            email=email,
            birth_date=birth_date,
            is_verified=False,
            welcome_seen=False
        )
        new_user.set_password(password)
        new_user.start_date = date.today().replace(day=1)
        
        db.session.add(new_user)
        db.session.commit()
        
        # Cria dados padrão...
        default_account = BankAccount(user_id=new_user.id, name='Carteira de dinheiro', current_balance=0.0)
        db.session.add(default_account)
        
        # Categorias Padrão (Resumido para economizar espaço visual, mas mantenha as suas)
        default_cats = [
            ('Salário', 'receita', '#10b981'), ('Investimentos', 'receita', '#10b981'), 
            ('Extras', 'receita', '#10b981'), ('Moradia', 'despesa', '#ef4444'), 
            ('Alimentação', 'despesa', '#ef4444'), ('Transporte', 'despesa', '#ef4444'), 
            ('Saúde', 'despesa', '#ef4444'), ('Educação', 'despesa', '#ef4444'), 
            ('Lazer', 'despesa', '#ef4444'), ('Compras', 'despesa', '#ef4444'),
            ('Transferência', 'transferencia', '#3B82F6'), ('Pagamento', 'pagamento', '#EF4444')
        ]
        for cn, ct, cc in default_cats:
            db.session.add(Category(user_id=new_user.id, name=cn, type=ct, color_hex=cc))
            
        db.session.commit()
        
        # --- Envio de E-mail BONITO ---
        token = generate_confirmation_token(new_user.email)
        confirm_url = url_for('auth.confirm_email', token=token, _external=True)
        
        # Renderiza o template de ativação
        html_content = render_template(
            'email/activate.html',
            user=new_user,
            confirm_url=confirm_url,
            current_year=datetime.now().year
        )

        try:
            send_email(
                to_email=new_user.email,
                subject="Bem-vindo! Confirme sua conta",
                html_content=html_content
            )
            flash('Cadastro realizado! Verifique seu e-mail para ativar a conta.', 'info')
        except Exception as e:
            print(f"Erro email: {e}")
            flash('Erro ao enviar e-mail de confirmação. Contate o suporte.', 'danger')

        logout_user()
        return redirect(url_for('auth.login'))
        
    return render_template('register.html')

# (Manter rota /confirm/<token> igual)
@auth_bp.route('/confirm/<token>')
def confirm_email(token):
    logout_user()
    try:
        email = confirm_token(token)
    except:
        flash('O link de confirmação é inválido ou expirou.', 'danger')
        return redirect(url_for('auth.login'))
        
    user = User.query.filter_by(email=email).first_or_404()
    
    if user.is_verified:
        flash('Conta já confirmada. Faça login.', 'success')
    else:
        user.is_verified = True
        user.welcome_seen = False
        db.session.add(user)
        db.session.commit()
        flash('Sua conta foi confirmada! Você já pode fazer login.', 'success')
        
    return redirect(url_for('auth.login'))

# (Manter rotas de 2FA e Login/Logout iguais)
# ...

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
        trust_device = request.form.get('trust_device')
        if code: code = code.replace(" ", "")
        
        totp = get_totp_object(user)
        
        if totp.verify(code, valid_window=1):
            remember = session.get('2fa_remember', False)
            session.pop('2fa_user_id', None)
            session.pop('2fa_remember', None)
            
            login_user(user, remember=remember)
            resp = make_response(redirect(url_for('finance.dashboard')))
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
            
            # Renderiza template de recuperação
            html_content = render_template(
                'email/reset_password.html',
                user=user,
                action_url=link,
                current_year=datetime.now().year
            )

            try:
                send_email(
                    to_email=user.email,
                    subject="Recuperação de Senha",
                    html_content=html_content
                )
            except Exception as e:
                print(f"Erro email: {e}")
                
        flash('Se o e-mail existir, as instruções foram enviadas.', 'info')
        return redirect(url_for('auth.login'))
    return render_template('forgot_password.html')

# (Manter o restante do arquivo igual: reset-password, settings/2fa/*, api/mark-welcome-seen)
# ...
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

@auth_bp.route('/settings/2fa/setup', methods=['POST'])
@login_required
def setup_2fa():
    method = request.form.get('method')
    if not current_user.two_factor_secret:
        current_user.two_factor_secret = pyotp.random_base32()
        db.session.commit()
    resp = {'status': 'ok', 'method': method, 'secret': current_user.two_factor_secret}
    if method == 'app':
        totp = pyotp.TOTP(current_user.two_factor_secret)
        uri = totp.provisioning_uri(name=current_user.email, issuer_name='Financeiro App')
        img = qrcode.make(uri)
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()
        resp['qr_code'] = f"data:image/png;base64,{img_str}"
    elif method == 'email':
        try:
            send_2fa_email(current_user, method='email')
        except Exception as e:
            return jsonify({'status': 'error', 'message': 'Erro ao enviar e-mail.'}), 500
    return jsonify(resp)

@auth_bp.route('/settings/2fa/enable', methods=['POST'])
@login_required
def enable_2fa():
    code = request.form.get('code')
    method = request.form.get('method')
    trust_device = request.form.get('trust_device')
    if code: code = code.replace(" ", "")
    if method == 'email':
        totp = pyotp.TOTP(current_user.two_factor_secret, interval=3600)
    else:
        totp = pyotp.TOTP(current_user.two_factor_secret)
    if totp.verify(code, valid_window=1):
        current_user.two_factor_method = method
        db.session.commit()
        flash(f'Autenticação de Dois Fatores ({method.upper()}) ativada com sucesso!', 'success')
        resp = make_response(redirect(url_for('settings.index', tab='account')))
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

@auth_bp.route('/api/mark-welcome-seen', methods=['POST'])
@login_required
def mark_welcome_seen():
    try:
        user = User.query.get(current_user.id)
        user.welcome_seen = True
        db.session.commit()
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500