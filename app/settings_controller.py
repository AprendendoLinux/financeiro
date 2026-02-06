from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, session
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash
from app import db
# CORREÇÃO: Removido MonthlyClosing da importação
from app.models import Category, BankAccount, CreditCard, FixedExpense, FixedRevenue, Transaction
from datetime import datetime, date
import os
import secrets
from app.email_utils import send_email 

settings_bp = Blueprint('settings', __name__)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@settings_bp.route('/settings')
@login_required
def index():
    active_tab = request.args.get('tab', 'categories')
    # used_colors não é mais necessário na view, mas mantemos compatibilidade se precisar
    return render_template('components/settings.html', 
                         user=current_user, 
                         active_tab=active_tab)

# --- CATEGORIAS ---
@settings_bp.route('/settings/category/add', methods=['POST'])
@login_required
def add_category():
    name = request.form.get('name')
    cat_type = request.form.get('type')
    
    # Lógica de Cor Automática
    # Receita = Verde Emerald (#10B981)
    # Despesa = Vermelho Red (#EF4444)
    color = '#10B981' if cat_type == 'receita' else '#EF4444'
    
    if Category.query.filter_by(user_id=current_user.id, name=name, type=cat_type).first():
        flash('Categoria já existe.', 'warning')
    else:
        new_cat = Category(user_id=current_user.id, name=name, type=cat_type, color_hex=color)
        db.session.add(new_cat)
        db.session.commit()
        flash('Categoria adicionada!', 'success')
    return redirect(url_for('settings.index', tab='categories'))

@settings_bp.route('/settings/category/edit/<int:id>', methods=['POST'])
@login_required
def edit_category(id):
    cat = Category.query.get_or_404(id)
    if cat.user_id != current_user.id: return redirect(url_for('settings.index'))
    
    cat.name = request.form.get('name')
    # Mantém a cor original ou atualiza baseado no tipo se necessário (aqui mantemos a original)
    db.session.commit()
    flash('Categoria atualizada!', 'success')
    return redirect(url_for('settings.index', tab='categories'))

@settings_bp.route('/settings/category/delete/<int:id>')
@login_required
def delete_category(id):
    cat = Category.query.get_or_404(id)
    if cat.user_id != current_user.id: return redirect(url_for('settings.index'))
    
    # Proteção para categoria de sistema (Transferência e Pagamento)
    if cat.type in ['transferencia', 'pagamento']:
        flash('Esta é uma categoria de sistema e não pode ser excluída.', 'warning')
        return redirect(url_for('settings.index', tab='categories'))

    # Verifica uso em transações
    if Transaction.query.filter_by(category_id=id).first():
        flash('Não é possível excluir: existem transações usando esta categoria.', 'danger')
    # Verifica uso em fixos
    elif FixedExpense.query.filter_by(category_id=id).first() or FixedRevenue.query.filter_by(category_id=id).first():
        flash('Não é possível excluir: existem despesas/receitas fixas usando esta categoria.', 'danger')
    else:
        db.session.delete(cat)
        db.session.commit()
        flash('Categoria removida!', 'success')
    return redirect(url_for('settings.index', tab='categories'))

# --- CONTAS ---
@settings_bp.route('/settings/account/add', methods=['POST'])
@login_required
def add_account():
    name = request.form.get('name')
    initial = float(request.form.get('initial_balance', 0))
    
    new_acc = BankAccount(user_id=current_user.id, name=name, current_balance=initial)
    db.session.add(new_acc)
    db.session.commit()
    flash('Conta adicionada!', 'success')
    return redirect(url_for('settings.index', tab='accounts'))

@settings_bp.route('/settings/account/edit/<int:id>', methods=['POST'])
@login_required
def edit_account(id):
    acc = BankAccount.query.get_or_404(id)
    if acc.user_id != current_user.id: return redirect(url_for('settings.index'))
    
    acc.name = request.form.get('name')
    db.session.commit()
    flash('Conta atualizada!', 'success')
    return redirect(url_for('settings.index', tab='accounts'))

@settings_bp.route('/settings/account/delete/<int:id>')
@login_required
def delete_account(id):
    acc = BankAccount.query.get_or_404(id)
    if acc.user_id != current_user.id: return redirect(url_for('settings.index'))
    
    if Transaction.query.filter_by(account_id=id).first():
        flash('Conta possui transações vinculadas e não pode ser excluída.', 'danger')
    else:
        # Desvincula de fixos antes de deletar (opcional, mas seguro)
        FixedExpense.query.filter_by(account_id=id).update({FixedExpense.account_id: None})
        FixedRevenue.query.filter_by(account_id=id).update({FixedRevenue.account_id: None})
        
        db.session.delete(acc)
        db.session.commit()
        flash('Conta removida!', 'success')
    return redirect(url_for('settings.index', tab='accounts'))

# --- CARTÕES ---
@settings_bp.route('/settings/card/add', methods=['POST'])
@login_required
def add_card():
    name = request.form.get('name')
    limit = float(request.form.get('limit'))
    closing = int(request.form.get('closing_day'))
    due = int(request.form.get('due_day'))
    
    initial_invoice_val = request.form.get('initial_invoice_value')
    if not initial_invoice_val:
        initial_invoice = 0.0
    else:
        initial_invoice = float(initial_invoice_val)
    
    new_card = CreditCard(
        user_id=current_user.id, name=name, limit_amount=limit,
        closing_day=closing, due_day=due
    )
    db.session.add(new_card)
    db.session.flush() # Gera o ID

    # Se houver gasto inicial, lança como transação para compor a fatura
    if initial_invoice > 0:
        today = date.today()
        t = Transaction(
            user_id=current_user.id,
            description="Saldo Inicial/Anterior",
            amount=initial_invoice,
            date=today,
            type='despesa',
            card_id=new_card.id,
            category_id=None
        )
        db.session.add(t)

    db.session.commit()
    flash('Cartão adicionado!', 'success')
    return redirect(url_for('settings.index', tab='cards'))

@settings_bp.route('/settings/card/edit/<int:id>', methods=['POST'])
@login_required
def edit_card(id):
    card = CreditCard.query.get_or_404(id)
    if card.user_id != current_user.id: return redirect(url_for('settings.index'))
    
    card.name = request.form.get('name')
    card.limit_amount = float(request.form.get('limit'))
    card.closing_day = int(request.form.get('closing_day'))
    card.due_day = int(request.form.get('due_day'))
    
    db.session.commit()
    flash('Cartão atualizada!', 'success')
    return redirect(url_for('settings.index', tab='cards'))

@settings_bp.route('/settings/card/delete/<int:id>')
@login_required
def delete_card(id):
    card = CreditCard.query.get_or_404(id)
    if card.user_id != current_user.id: return redirect(url_for('settings.index'))
    
    if Transaction.query.filter_by(card_id=id).first():
        flash('Cartão possui faturas/compras e não pode ser excluído.', 'danger')
    else:
        FixedExpense.query.filter_by(card_id=id).update({FixedExpense.card_id: None})
        db.session.delete(card)
        db.session.commit()
        flash('Cartão removido!', 'success')
    return redirect(url_for('settings.index', tab='cards'))

# --- FIXOS ---
@settings_bp.route('/settings/fixed/add', methods=['POST'])
@login_required
def add_fixed():
    desc = request.form.get('description')
    amount = float(request.form.get('amount'))
    day = int(request.form.get('day'))
    cat_id = int(request.form.get('category_id'))
    
    payment_method = request.form.get('payment_method')
    
    acc_id = None
    card_id = None

    if payment_method == 'credit':
        card_id = int(request.form.get('card_id'))
    else:
        acc_id = int(request.form.get('account_id'))
    
    new_fix = FixedExpense(
        user_id=current_user.id, description=desc, amount=amount,
        day_of_month=day, category_id=cat_id, 
        account_id=acc_id, card_id=card_id
    )
    db.session.add(new_fix)
    db.session.commit()
    flash('Despesa fixa agendada!', 'success')
    return redirect(url_for('settings.index', tab='fixed'))

@settings_bp.route('/settings/fixed/edit/<int:id>', methods=['POST'])
@login_required
def edit_fixed(id):
    fix = FixedExpense.query.get_or_404(id)
    if fix.user_id != current_user.id: return redirect(url_for('settings.index'))
    
    fix.description = request.form.get('description')
    fix.amount = float(request.form.get('amount'))
    fix.day_of_month = int(request.form.get('day'))
    fix.category_id = int(request.form.get('category_id'))
    
    payment_method = request.form.get('payment_method')
    
    if payment_method == 'credit':
        fix.card_id = int(request.form.get('card_id'))
        fix.account_id = None
    else:
        fix.account_id = int(request.form.get('account_id'))
        fix.card_id = None
    
    db.session.commit()
    flash('Despesa fixa atualizada!', 'success')
    
    origin = request.form.get('origin')
    if origin and 'dashboard' in origin:
        return redirect(url_for('finance.dashboard'))
    return redirect(url_for('settings.index', tab='fixed'))

@settings_bp.route('/settings/fixed/delete/<int:id>')
@login_required
def delete_fixed(id):
    fix = FixedExpense.query.get_or_404(id)
    if fix.user_id != current_user.id: return redirect(url_for('settings.index'))
    
    try:
        # Desvincula transações passadas para evitar erro de integridade
        Transaction.query.filter_by(fixed_expense_id=id).update({Transaction.fixed_expense_id: None})
        
        db.session.delete(fix)
        db.session.commit()
        flash('Despesa fixa encerrada! O histórico foi mantido.', 'success')
    except Exception as e:
        db.session.rollback()
        print(f"Erro ao deletar fixo: {e}")
        flash('Erro ao excluir item fixo.', 'danger')

    return redirect(url_for('finance.dashboard'))

@settings_bp.route('/settings/revenue/add', methods=['POST'])
@login_required
def add_fixed_revenue():
    desc = request.form.get('description')
    amount = float(request.form.get('amount'))
    day = int(request.form.get('day'))
    cat_id = int(request.form.get('category_id'))
    acc_id = int(request.form.get('account_id'))
    
    new_rev = FixedRevenue(
        user_id=current_user.id, description=desc, amount=amount,
        day_of_month=day, category_id=cat_id, account_id=acc_id
    )
    db.session.add(new_rev)
    db.session.commit()
    flash('Receita fixa agendada!', 'success')
    return redirect(url_for('settings.index', tab='revenues'))

@settings_bp.route('/settings/revenue/edit/<int:id>', methods=['POST'])
@login_required
def edit_fixed_revenue(id):
    rev = FixedRevenue.query.get_or_404(id)
    if rev.user_id != current_user.id: return redirect(url_for('settings.index'))
    
    rev.description = request.form.get('description')
    rev.amount = float(request.form.get('amount'))
    rev.day_of_month = int(request.form.get('day'))
    rev.category_id = int(request.form.get('category_id'))
    rev.account_id = int(request.form.get('account_id'))
    
    db.session.commit()
    flash('Receita fixa atualizada!', 'success')

    origin = request.form.get('origin')
    if origin and 'dashboard' in origin:
        return redirect(url_for('finance.dashboard'))
    return redirect(url_for('settings.index', tab='revenues'))

@settings_bp.route('/settings/revenue/delete/<int:id>')
@login_required
def delete_fixed_revenue(id):
    rev = FixedRevenue.query.get_or_404(id)
    if rev.user_id != current_user.id: return redirect(url_for('settings.index'))
    
    try:
        # Desvincula transações passadas
        Transaction.query.filter_by(fixed_revenue_id=id).update({Transaction.fixed_revenue_id: None})
        
        db.session.delete(rev)
        db.session.commit()
        flash('Receita fixa encerrada! O histórico foi mantido.', 'success')
    except Exception as e:
        db.session.rollback()
        print(f"Erro ao deletar receita fixa: {e}")
        flash('Erro ao excluir item fixo.', 'danger')

    return redirect(url_for('finance.dashboard'))

# --- MINHA CONTA & PERFIL ---

@settings_bp.route('/settings/profile/update', methods=['POST'])
@login_required
def update_profile():
    name = request.form.get('name')
    last_name = request.form.get('last_name')
    
    current_user.name = name
    current_user.last_name = last_name
    db.session.commit()
    flash('Dados pessoais atualizados com sucesso!', 'success')
    return redirect(url_for('settings.index', tab='account'))

@settings_bp.route('/settings/profile/avatar', methods=['POST'])
@login_required
def upload_avatar():
    if 'avatar' not in request.files:
        flash('Nenhum arquivo enviado.', 'danger')
        return redirect(url_for('settings.index', tab='account'))
    
    file = request.files['avatar']
    
    if file.filename == '':
        flash('Nenhum arquivo selecionado.', 'danger')
        return redirect(url_for('settings.index', tab='account'))
        
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        unique_filename = f"{current_user.id}_{int(datetime.utcnow().timestamp())}_{filename}"
        
        upload_folder = os.path.join(current_app.root_path, 'static', 'uploads')
        if not os.path.exists(upload_folder):
            os.makedirs(upload_folder)
            
        file.save(os.path.join(upload_folder, unique_filename))
        
        if current_user.avatar_path:
            old_path = os.path.join(upload_folder, current_user.avatar_path)
            if os.path.exists(old_path):
                try: os.remove(old_path)
                except Exception as e: print(f"Erro ao deletar avatar antigo: {e}")

        current_user.avatar_path = unique_filename
        db.session.commit()
        flash('Foto de perfil atualizada!', 'success')
    else:
        flash('Tipo de arquivo não permitido (apenas PNG, JPG, JPEG, GIF).', 'danger')
        
    return redirect(url_for('settings.index', tab='account'))

@settings_bp.route('/settings/security/email', methods=['POST'])
@login_required
def request_email_change():
    new_email = request.form.get('new_email')
    
    if not new_email or new_email == current_user.email:
        flash('E-mail inválido ou igual ao atual.', 'warning')
        return redirect(url_for('settings.index', tab='account'))
        
    token = secrets.token_urlsafe(32)
    current_user.pending_email = new_email
    current_user.auth_token = token
    current_user.token_expiration = datetime.utcnow().replace(hour=23, minute=59) 
    
    db.session.commit()
    
    link = url_for('settings.confirm_email_change', token=token, _external=True)
    try:
        send_email(
            to_email=new_email,
            subject="Confirme seu novo e-mail",
            title="Alteração de E-mail",
            body_content=f"Olá {current_user.name}. Recebemos uma solicitação para alterar seu e-mail de cadastro. Clique no botão abaixo para confirmar a mudança.",
            action_url=link,
            action_text="Confirmar Novo E-mail"
        )
        flash(f'Link de confirmação enviado para {new_email}. Verifique sua caixa de entrada.', 'info')
    except Exception as e:
        print(f"Erro no envio de email: {e}")
        flash('Erro ao enviar e-mail. Tente novamente mais tarde.', 'danger')
        
    return redirect(url_for('settings.index', tab='account'))

@settings_bp.route('/settings/confirm_email/<token>')
def confirm_email_change(token):
    session.clear()
    
    from app.models import User
    user = User.query.filter_by(auth_token=token).first()
        
    if not user:
        flash('Link inválido ou expirado.', 'danger')
        return redirect(url_for('auth.login'))
        
    user.email = user.pending_email
    user.pending_email = None
    user.auth_token = None
    user.is_verified = True
    db.session.commit()
    
    flash('E-mail alterado com sucesso! Faça login com o novo endereço.', 'success')
    return redirect(url_for('auth.login'))

@settings_bp.route('/settings/security/password', methods=['POST'])
@login_required
def change_password():
    current_pass = request.form.get('current_password')
    new_pass = request.form.get('new_password')
    confirm_pass = request.form.get('confirm_password')
    
    if not current_user.check_password(current_pass):
        flash('Senha atual incorreta.', 'danger')
        return redirect(url_for('settings.index', tab='account'))
        
    if new_pass != confirm_pass:
        flash('As novas senhas não coincidem.', 'warning')
        return redirect(url_for('settings.index', tab='account'))
        
    if len(new_pass) < 6:
        flash('A nova senha deve ter pelo menos 6 caracteres.', 'warning')
        return redirect(url_for('settings.index', tab='account'))
        
    current_user.password_hash = generate_password_hash(new_pass)
    db.session.commit()
    
    flash('Senha atualizada com sucesso!', 'success')
    return redirect(url_for('settings.index', tab='account'))

@settings_bp.route('/settings/account/reset', methods=['POST'])
@login_required
def reset_data():
    password = request.form.get('password')
    # ALTERAÇÃO: Removido start_option e retro_date. Data sempre é HOJE.

    if not current_user.check_password(password):
        flash('Senha incorreta. Operação cancelada.', 'danger')
        return redirect(url_for('settings.index', tab='account'))

    # ALTERAÇÃO: Força a data de início para ser sempre HOJE
    new_start_date = date.today()

    try:
        Transaction.query.filter_by(user_id=current_user.id).delete()
        # CORREÇÃO: Linha de MonthlyClosing removida
        FixedExpense.query.filter_by(user_id=current_user.id).delete()
        FixedRevenue.query.filter_by(user_id=current_user.id).delete()
        
        for card in current_user.cards: db.session.delete(card)
        for acc in current_user.accounts: db.session.delete(acc)
        for cat in current_user.categories: db.session.delete(cat)
        
        default_account = BankAccount(user_id=current_user.id, name='Carteira de dinheiro', current_balance=0.0)
        db.session.add(default_account)

        default_cats = [
            ('Salário', 'receita', '#10b981'), ('Investimentos', 'receita', '#10b981'), 
            ('Extras', 'receita', '#10b981'),
            ('Moradia', 'despesa', '#ef4444'), ('Alimentação', 'despesa', '#ef4444'), 
            ('Transporte', 'despesa', '#ef4444'), ('Saúde', 'despesa', '#ef4444'),
            ('Educação', 'despesa', '#ef4444'), ('Lazer', 'despesa', '#ef4444'),
            ('Compras', 'despesa', '#ef4444'),
            ('Transferência', 'transferencia', '#3B82F6'), # Categoria do Sistema
            ('Pagamento', 'pagamento', '#EF4444')         # Nova Categoria de Pagamento
        ]
        for cn, ct, cc in default_cats:
            db.session.add(Category(user_id=current_user.id, name=cn, type=ct, color_hex=cc))

        current_user.start_date = new_start_date
        db.session.commit()
        flash(f'Dados zerados com sucesso! O sistema foi restaurado. Início definido para {new_start_date.strftime("%d/%m/%Y")}.', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash('Erro ao zerar dados.', 'danger')
        print(e)

    return redirect(url_for('finance.dashboard'))

@settings_bp.route('/settings/account/delete', methods=['POST'])
@login_required
def delete_user_account():
    password = request.form.get('password')
    
    if not current_user.check_password(password):
        flash('Senha incorreta. Operação cancelada.', 'danger')
        return redirect(url_for('settings.index', tab='account'))
    
    try:
        Transaction.query.filter_by(user_id=current_user.id).delete()
        # CORREÇÃO: Linha de MonthlyClosing removida
        FixedExpense.query.filter_by(user_id=current_user.id).delete()
        FixedRevenue.query.filter_by(user_id=current_user.id).delete()
        
        for card in current_user.cards: db.session.delete(card)
        for acc in current_user.accounts: db.session.delete(acc)
        for cat in current_user.categories: db.session.delete(cat)
        
        db.session.delete(current_user)
        db.session.commit()
        
        flash('Sua conta foi excluída permanentemente.', 'info')
        return redirect(url_for('auth.login'))
        
    except Exception as e:
        db.session.rollback()
        flash('Erro ao excluir conta.', 'danger')
        print(e)
        return redirect(url_for('settings.index', tab='account'))