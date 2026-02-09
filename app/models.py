from app import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import pyotp # Adicionado para 2FA

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    
    # Dados Pessoais
    name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=True)
    birth_date = db.Column(db.Date, nullable=True)
    start_date = db.Column(db.Date, nullable=True)
    avatar_path = db.Column(db.String(200), nullable=True)

    # Segurança e Verificação
    is_verified = db.Column(db.Boolean, default=False)
    auth_token = db.Column(db.String(100), nullable=True, unique=True)
    token_expiration = db.Column(db.DateTime, nullable=True)
    pending_email = db.Column(db.String(150), nullable=True)

    # Controle de Onboarding (Esta era a coluna que faltava)
    welcome_seen = db.Column(db.Boolean, default=False)

    # NOVAS COLUNAS 2FA
    two_factor_secret = db.Column(db.String(32), nullable=True)
    two_factor_method = db.Column(db.String(10), nullable=True) # 'app' ou 'email'
    backup_codes = db.Column(db.Text, nullable=True)

    # Relacionamentos
    categories = db.relationship('Category', backref='user', lazy=True, cascade="all, delete-orphan")
    accounts = db.relationship('BankAccount', backref='user', lazy=True, cascade="all, delete-orphan")
    cards = db.relationship('CreditCard', backref='user', lazy=True, cascade="all, delete-orphan")
    
    # Transações e Fixos
    transactions = db.relationship('Transaction', backref='user', lazy=True)
    fixed_expenses = db.relationship('FixedExpense', backref='user', lazy=True)
    fixed_revenues = db.relationship('FixedRevenue', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    # Método auxiliar para gerar URI do QR Code
    def get_totp_uri(self):
        if not self.two_factor_secret:
            return None
        return pyotp.totp.TOTP(self.two_factor_secret).provisioning_uri(
            name=self.email, 
            issuer_name='Financeiro App'
        )

class Category(db.Model):
    __tablename__ = 'categories'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(20), nullable=False) 
    color_hex = db.Column(db.String(7), default="#64748b")

class BankAccount(db.Model):
    __tablename__ = 'bank_accounts'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    current_balance = db.Column(db.Numeric(10, 2), default=0.0)

class CreditCard(db.Model):
    __tablename__ = 'credit_cards'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    limit_amount = db.Column(db.Numeric(10, 2), nullable=False)
    closing_day = db.Column(db.Integer, nullable=False)
    due_day = db.Column(db.Integer, nullable=False)
    
    brand = db.Column(db.String(50), default='other') 
    bank = db.Column(db.String(50), default='other')

class FixedExpense(db.Model):
    __tablename__ = 'fixed_expenses'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    description = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    day_of_month = db.Column(db.Integer, nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'))
    account_id = db.Column(db.Integer, db.ForeignKey('bank_accounts.id'))
    card_id = db.Column(db.Integer, db.ForeignKey('credit_cards.id')) 
    
    category = db.relationship('Category')
    account = db.relationship('BankAccount')
    card = db.relationship('CreditCard')

class FixedRevenue(db.Model):
    __tablename__ = 'fixed_revenues'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    description = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    day_of_month = db.Column(db.Integer, nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'))
    account_id = db.Column(db.Integer, db.ForeignKey('bank_accounts.id'))
    
    category = db.relationship('Category')
    account = db.relationship('BankAccount')

class Transaction(db.Model):
    __tablename__ = 'transactions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    description = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    date = db.Column(db.Date, nullable=False)
    
    created_at = db.Column(db.DateTime, default=datetime.now)

    type = db.Column(db.String(20), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=True)
    account_id = db.Column(db.Integer, db.ForeignKey('bank_accounts.id'), nullable=True)
    card_id = db.Column(db.Integer, db.ForeignKey('credit_cards.id'), nullable=True)
    fixed_expense_id = db.Column(db.Integer, db.ForeignKey('fixed_expenses.id'), nullable=True)
    fixed_revenue_id = db.Column(db.Integer, db.ForeignKey('fixed_revenues.id'), nullable=True)
    installment_identifier = db.Column(db.String(50), nullable=True)
    installment_current = db.Column(db.Integer, nullable=True)
    installment_total = db.Column(db.Integer, nullable=True)
    
    category = db.relationship('Category')
    account = db.relationship('BankAccount')
    card = db.relationship('CreditCard')