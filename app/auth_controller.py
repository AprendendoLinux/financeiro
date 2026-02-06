from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from app import db
from app.models import User, Category, BankAccount
from app.email_utils import send_email
from datetime import date, datetime, timedelta
import re
import secrets

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

# --- ROTAS ---

@auth_bp.route('/', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('finance.dashboard'))
        
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            if not user.is_verified:
                flash('Sua conta ainda não foi ativada. Verifique seu e-mail.', 'warning')
                return render_template('login.html')

            login_user(user)
            return redirect(url_for('finance.dashboard'))
        else:
            flash('E-mail ou senha incorretos.', 'danger')
            
    return render_template('login.html')

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('finance.dashboard'))
        
    if request.method == 'POST':
        first_name = request.form.get('name')
        last_name = request.form.get('last_name')
        birth_date_str = request.form.get('birth_date') # Captura Data de Nascimento
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # Processamento de Datas
        try:
            birth_date = datetime.strptime(birth_date_str, '%Y-%m-%d').date() if birth_date_str else None
        except ValueError:
            birth_date = None

        start_date_str = request.form.get('start_date')
        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            except ValueError:
                start_date = date.today()
        else:
            start_date = date.today()
        
        # Validações
        if not validate_email_format(email):
            flash('Formato de e-mail inválido.', 'warning')
            return redirect(url_for('auth.register'))
            
        if User.query.filter_by(email=email).first():
            flash('E-mail já cadastrado.', 'warning')
            return redirect(url_for('auth.register'))
            
        if password != confirm_password:
            flash('Senhas não conferem.', 'warning')
            return redirect(url_for('auth.register'))
            
        if not validate_password_complexity(password):
            flash('A senha deve ter no mínimo 6 caracteres, incluir uma maiúscula, um número e um símbolo.', 'warning')
            return redirect(url_for('auth.register'))
            
        # Criação do Usuário
        new_user = User(
            name=first_name,
            last_name=last_name,
            email=email,
            password_hash=generate_password_hash(password),
            birth_date=birth_date, # Salva Data de Nascimento
            start_date=start_date,
            is_verified=False
        )
        
        token = secrets.token_urlsafe(32)
        new_user.auth_token = token
        new_user.token_expiration = datetime.utcnow() + timedelta(hours=24)

        db.session.add(new_user)
        db.session.commit()
        
        # --- DADOS PADRÃO ---
        default_account = BankAccount(user_id=new_user.id, name='Carteira de dinheiro', current_balance=0.0)
        db.session.add(default_account)
        
        default_cats = [
            ('Salário', 'receita', '#10b981'), 
            ('Investimentos', 'receita', '#10b981'),
            ('Extras', 'receita', '#10b981'), 
            ('Moradia', 'despesa', '#ef4444'), 
            ('Alimentação', 'despesa', '#ef4444'),
            ('Transporte', 'despesa', '#ef4444'), 
            ('Saúde', 'despesa', '#ef4444'),
            ('Educação', 'despesa', '#ef4444'), 
            ('Lazer', 'despesa', '#ef4444'),
            ('Compras', 'despesa', '#ef4444')
        ]
        
        for cn, ct, cc in default_cats:
            db.session.add(Category(user_id=new_user.id, name=cn, type=ct, color_hex=cc))
            
        db.session.commit()
        
        session.clear() 

        confirm_link = url_for('auth.confirm_email', token=token, _external=True)
        try:
            send_email(
                to_email=email,
                subject="Ative sua conta",
                title="Bem-vindo ao Financeiro!",
                body_content=f"Olá {first_name}, obrigado por se cadastrar. Clique no botão abaixo para ativar sua conta.",
                action_url=confirm_link,
                action_text="Ativar Conta"
            )
            flash('Cadastro realizado! Verifique seu e-mail para ativar a conta.', 'success')
        except Exception as e:
            print(f"Erro de envio de email: {e}")
            flash('Erro ao enviar e-mail de ativação. Contate o suporte.', 'warning')
        
        return redirect(url_for('auth.login'))
        
    return render_template('register.html')

@auth_bp.route('/confirm/<token>')
def confirm_email(token):
    user = User.query.filter_by(auth_token=token).first()
    
    if not user:
        flash('Link de ativação inválido.', 'danger')
        return redirect(url_for('auth.login'))
        
    if user.token_expiration and user.token_expiration < datetime.utcnow():
        flash('Link expirado. Faça login para solicitar um novo.', 'warning')
        return redirect(url_for('auth.login'))
        
    user.is_verified = True
    user.auth_token = None
    user.token_expiration = None
    db.session.commit()
    
    session.clear()
    
    flash('Conta ativada! Faça login para continuar.', 'success')
    return redirect(url_for('auth.login'))

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
            
            reset_link = url_for('auth.reset_password', token=token, _external=True)
            
            try:
                send_email(
                    to_email=user.email,
                    subject="Recuperação de Senha",
                    title="Redefinir Senha",
                    body_content=f"Olá {user.name}. Recebemos uma solicitação para redefinir sua senha.",
                    action_url=reset_link,
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

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Você saiu do sistema.', 'info')
    return redirect(url_for('auth.login'))