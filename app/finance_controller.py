from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from sqlalchemy import extract, func, or_, and_
from decimal import Decimal
import uuid
import calendar
import re 

from app import db
from app.models import Transaction, BankAccount, FixedExpense, FixedRevenue, CreditCard, Category
from app.transaction_service import TransactionService

finance_bp = Blueprint('finance', __name__)

MONTH_NAMES = {
    1: 'JANEIRO', 2: 'FEVEREIRO', 3: 'MARÇO', 4: 'ABRIL', 5: 'MAIO', 6: 'JUNHO',
    7: 'JULHO', 8: 'AGOSTO', 9: 'SETEMBRO', 10: 'OUTUBRO', 11: 'NOVEMBRO', 12: 'DEZEMBRO'
}

# --- FUNÇÃO AUXILIAR: GERADOR DE PARCELAS FIXAS ---
def generate_fixed_installments(fixed_expense, start_date, months=12):
    created_count = 0
    current_dt = start_date
    
    for i in range(months):
        target_date = TransactionService.get_safe_date(current_dt.year, current_dt.month, fixed_expense.day_of_month)
        
        new_trans = Transaction(
            user_id=fixed_expense.user_id,
            description=fixed_expense.description,
            amount=fixed_expense.amount,
            date=target_date,
            type='despesa',
            category_id=fixed_expense.category_id,
            account_id=None,
            card_id=fixed_expense.card_id,
            fixed_expense_id=fixed_expense.id
        )
        db.session.add(new_trans)
        created_count += 1
        current_dt = current_dt + relativedelta(months=1)
        
    return created_count

# --- NOVA FUNÇÃO: RENOVAÇÃO AUTOMÁTICA ---
def check_and_renew_fixed_expenses(user_id):
    fixed_cards = FixedExpense.query.filter_by(user_id=user_id).filter(FixedExpense.card_id != None).all()
    
    renewed_count = 0
    today = date.today()
    safety_horizon = today + relativedelta(months=3)

    for fixed in fixed_cards:
        last_trans = Transaction.query.filter_by(fixed_expense_id=fixed.id).order_by(Transaction.date.desc()).first()
        
        if last_trans:
            if last_trans.date < safety_horizon:
                start_next = last_trans.date + relativedelta(months=1)
                count = generate_fixed_installments(fixed, start_next, 12)
                if count > 0:
                    renewed_count += 1
    
    if renewed_count > 0:
        db.session.commit()

@finance_bp.route('/dashboard')
@login_required
def dashboard():
    check_and_renew_fixed_expenses(current_user.id)

    today = date.today()
    try:
        month = int(request.args.get('month', today.month))
        year = int(request.args.get('year', today.year))
    except ValueError:
        month = today.month
        year = today.year

    req_date = date(year, month, 1)
    if current_user.start_date:
        start_month = current_user.start_date.replace(day=1)
        if req_date < start_month:
            return redirect(url_for('finance.dashboard', month=start_month.month, year=start_month.year))

    last_db_trans = Transaction.query.filter_by(user_id=current_user.id).order_by(Transaction.date.desc()).first()
    max_nav_date = last_db_trans.date if last_db_trans else today
    if max_nav_date < today: max_nav_date = today

    next_view_date = date(year, month, 1) + relativedelta(months=1)
    allow_next = True
    if next_view_date > max_nav_date.replace(day=1): allow_next = False

    all_fixed_expenses = FixedExpense.query.filter_by(user_id=current_user.id).order_by(FixedExpense.day_of_month).all()
    fixed_account_expenses = [f for f in all_fixed_expenses if not f.card_id]
    fixed_revenues_defs = FixedRevenue.query.filter_by(user_id=current_user.id).order_by(FixedRevenue.day_of_month).all()

    ref_pattern = f"%Ref: {month:02d}/{year}%"
    
    transactions = Transaction.query.filter(
        Transaction.user_id == current_user.id,
        or_(
            and_(
                extract('month', Transaction.date) == month,
                extract('year', Transaction.date) == year
            ),
            Transaction.description.like(ref_pattern)
        ),
        Transaction.type.in_(['receita', 'despesa', 'transf_saida', 'transf_entrada']) 
    ).order_by(Transaction.date.desc(), Transaction.created_at.desc()).all()

    paid_expense_ids = []
    received_revenue_ids = []
    
    fixed_map = {}
    for t in transactions:
        is_anticipated = "(Ref:" in (t.description or "") or "(Repassado" in (t.description or "") or "(Antecipado)" in (t.description or "")
        if t.date > today and not is_anticipated and not t.account_id:
            t.is_scheduled = True
        else:
            t.is_scheduled = False

        if t.fixed_expense_id: paid_expense_ids.append(t.fixed_expense_id)
        if t.fixed_revenue_id: received_revenue_ids.append(t.fixed_revenue_id)

        if (t.fixed_expense_id or t.fixed_revenue_id) and t.is_scheduled:
            fid_col = Transaction.fixed_expense_id if t.fixed_expense_id else Transaction.fixed_revenue_id
            fid_val = t.fixed_expense_id or t.fixed_revenue_id
            pending = Transaction.query.filter(
                Transaction.user_id == current_user.id, fid_col == fid_val,
                Transaction.date < t.date, Transaction.date > today 
            ).first()
            t.is_locked_anticipate = bool(pending)

        fid = t.fixed_expense_id or t.fixed_revenue_id
        if fid:
            if fid not in fixed_map: fixed_map[fid] = []
            fixed_map[fid].append(t)

    for fid, items in fixed_map.items():
        if len(items) > 1:
            def get_ref_date(trans):
                match = re.search(r'Ref: (\d{2})/(\d{4})', trans.description)
                if match: return date(int(match.group(2)), int(match.group(1)), 1)
                return trans.date
            items.sort(key=get_ref_date)
            for i in range(len(items) - 1): items[i].is_locked_by_cascade = True
            items[-1].is_locked_by_cascade = False

    # Identificar categoria de Pagamento para excluir da soma
    pagamento_cats = Category.query.filter_by(user_id=current_user.id, type='pagamento').all()
    pagamento_ids = [c.id for c in pagamento_cats]

    # --- CÁLCULO DO BALANÇO REAL (O que de fato impactou o saldo HOJE) ---
    receitas_real = 0
    despesas_real = 0
    
    for t in transactions:
        if t.type == 'receita':
             receitas_real += t.amount
        elif t.type == 'despesa':
            # Filtro Crucial: Ignora Pagamento de Fatura na soma das despesas
            # (Pois as compras do cartão já serão somadas abaixo ou aqui mesmo)
            is_payment_cat = t.category_id in pagamento_ids
            is_payment_desc = "Pagamento Fatura" in (t.description or "") or "Pagamento de Cartão" in (t.description or "")
            
            if is_payment_cat or is_payment_desc:
                continue

            if t.card_id:
                if t.date <= today: despesas_real += t.amount
            else:
                despesas_real += t.amount
    
    receitas = receitas_real
    despesas = despesas_real
    saldo_mensal = receitas - despesas

    # --- CÁLCULO DA PREVISÃO (Saldo Final após tudo pago) ---
    
    # 1. Receitas: Fixas + Avulsas
    total_receitas_prev = sum(r.amount for r in fixed_revenues_defs)
    
    for t in transactions:
        if t.type == 'receita' and not t.fixed_revenue_id:
            total_receitas_prev += t.amount

    # 2. Despesas: Fixas de Conta + Avulsos de Conta (SEM PAGAMENTO DE FATURA) + Faturas Totais
    total_despesas_prev = sum(f.amount for f in fixed_account_expenses)
    
    for t in transactions:
        # Soma avulsos de conta (exclui pagamentos de fatura para não duplicar)
        if t.type == 'despesa' and not t.fixed_expense_id and not t.card_id:
            
            is_payment_cat = t.category_id in pagamento_ids
            is_payment_desc = "Pagamento Fatura" in (t.description or "") or "Pagamento de Cartão" in (t.description or "")
            
            if not is_payment_cat and not is_payment_desc:
                total_despesas_prev += t.amount

    # 3. Soma TOTAL das Faturas de Cartão (Isso representa o gasto real do cartão)
    for card in current_user.cards:
        open_date, close_date, _ = TransactionService.get_invoice_dates(card, month, year)
        
        # Soma TODAS as compras do cartão que caem nesta fatura (Fixas ou Avulsas)
        total_fatura = db.session.query(func.sum(Transaction.amount)).filter(
            Transaction.user_id == current_user.id,
            Transaction.card_id == card.id,
            Transaction.type == 'despesa',
            Transaction.date >= open_date,
            Transaction.date <= close_date
        ).scalar() or 0
        
        total_despesas_prev += total_fatura

    saldo_previsao = total_receitas_prev - total_despesas_prev
    
    saldo_contas = sum(acc.current_balance for acc in current_user.accounts)

    expenses_status = [{'obj': e, 'is_paid': e.id in paid_expense_ids} for e in fixed_account_expenses]
    revenues_status = [{'obj': r, 'is_received': r.id in received_revenue_ids} for r in fixed_revenues_defs]

    cards_data = []
    for card in current_user.cards:
        stats = TransactionService.get_card_stats(current_user.id, card.id, month, year)
        cards_data.append(stats)

    is_future_view = req_date.replace(day=1) > today.replace(day=1)

    return render_template('dashboard.html', 
                         transactions=transactions,
                         receitas=receitas,
                         despesas=despesas,
                         saldo_mensal=saldo_mensal,
                         saldo_previsao=saldo_previsao,
                         saldo_contas=saldo_contas,
                         current_month=month,
                         current_year=year,
                         month_name=MONTH_NAMES[month],
                         fixed_expenses=expenses_status, 
                         fixed_revenues=revenues_status,
                         cards_data=cards_data,
                         allow_next=allow_next,
                         is_future_view=is_future_view,
                         today=today)

@finance_bp.route('/transaction/add', methods=['POST'])
@login_required
def add_transaction():
    trans_type = request.form.get('type')
    description = request.form.get('description')
    amount = Decimal(request.form.get('amount', '0').replace(',', '.'))
    date_str = request.form.get('date')
    base_date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
    category_id = int(request.form.get('category_id'))
    
    if current_user.start_date:
        start_month = current_user.start_date.replace(day=1)
        if base_date_obj.replace(day=1) < start_month:
            flash(f'Operação não permitida. Seu início no sistema é {current_user.start_date.strftime("%m/%Y")}.', 'danger')
            return redirect(url_for('finance.dashboard'))
    
    payment_mode = request.form.get('payment_mode')
    account_id = None
    card_id = None
    installments = 1

    if trans_type == 'despesa':
        if payment_mode == 'account':
            account_id = int(request.form.get('account_id'))
        elif payment_mode == 'credit':
            card_id = int(request.form.get('card_id'))
            installments = int(request.form.get('installments', 1))
    else:
        account_id = int(request.form.get('account_id'))

    if request.form.get('is_fixed'):
        day_fixed = base_date_obj.day
        if trans_type == 'despesa':
            new_fixed = FixedExpense(
                user_id=current_user.id, description=description, amount=amount,
                day_of_month=day_fixed, category_id=category_id,
                account_id=account_id, card_id=card_id
            )
            db.session.add(new_fixed)
            db.session.flush()
            if card_id:
                generate_fixed_installments(new_fixed, base_date_obj, 12)
                flash('Despesa fixa de cartão cadastrada! Lançamentos gerados para 12 meses.', 'success')
            else:
                flash('Despesa fixa de conta cadastrada! Ative-a no painel para lançar.', 'info')
        elif trans_type == 'receita':
            new_fixed = FixedRevenue(
                user_id=current_user.id, description=description, amount=amount,
                day_of_month=day_fixed, category_id=category_id, account_id=account_id
            )
            db.session.add(new_fixed)
            flash('Receita fixa cadastrada! Ative-a no painel para lançar.', 'info')
    else:
        if trans_type == 'despesa':
            if payment_mode == 'account':
                account = BankAccount.query.get(account_id)
                if account.current_balance < amount:
                    flash(f'Saldo insuficiente na conta {account.name}.', 'danger')
                    return redirect(url_for('finance.dashboard', month=base_date_obj.month, year=base_date_obj.year))
                account.current_balance -= amount
            elif payment_mode == 'credit':
                can_buy, msg = TransactionService.check_card_limit(current_user.id, card_id, amount)
                if not can_buy:
                    flash(msg, 'danger')
                    return redirect(url_for('finance.dashboard'))
        else:
            account = BankAccount.query.get(account_id)
            account.current_balance += amount

        if trans_type == 'despesa' and payment_mode == 'credit' and installments > 1:
            card = CreditCard.query.get(card_id)
            identifier = str(uuid.uuid4())
            installment_value = amount / installments
            first_due_date = TransactionService.calculate_card_date(base_date_obj, card)
            
            for i in range(installments):
                due_date = first_due_date + relativedelta(months=i)
                new_trans = Transaction(
                    user_id=current_user.id,
                    description=f"{description} ({i+1}/{installments})",
                    amount=installment_value,
                    date=due_date,
                    type='despesa',
                    category_id=category_id,
                    card_id=card_id,
                    installment_total=installments,
                    installment_current=i+1,
                    installment_identifier=identifier,
                    total_purchase_amount=amount
                )
                db.session.add(new_trans)
            flash(f'Compra parcelada em {installments}x lançada!', 'success')
        else:
            final_date = base_date_obj
            if trans_type == 'despesa' and payment_mode == 'credit':
                 card = CreditCard.query.get(card_id)
                 final_date = TransactionService.calculate_card_date(base_date_obj, card)

            new_trans = Transaction(
                user_id=current_user.id, description=description, amount=amount,
                date=final_date, type=trans_type, category_id=category_id,
                account_id=account_id, card_id=card_id
            )
            db.session.add(new_trans)
            flash('Lançamento adicionado!', 'success')

    db.session.commit()
    return redirect(url_for('finance.dashboard', month=base_date_obj.month, year=base_date_obj.year))

@finance_bp.route('/transaction/delete/<int:id>')
@login_required
def delete_transaction(id):
    trans = Transaction.query.get_or_404(id)
    
    if trans.fixed_expense_id:
        fixed_id = trans.fixed_expense_id
        today = date.today()
        
        if trans.date > today:
            Transaction.query.filter(
                Transaction.fixed_expense_id == fixed_id,
                Transaction.date >= trans.date
            ).delete()
            
            Transaction.query.filter_by(fixed_expense_id=fixed_id).update({Transaction.fixed_expense_id: None})
            FixedExpense.query.filter_by(id=fixed_id).delete()
            
            db.session.commit()
            flash('Plano fixo cancelado e lançamentos futuros removidos.', 'success')
            return redirect(url_for('finance.dashboard', month=trans.date.month, year=trans.date.year))
        
        else:
            db.session.delete(trans)
            db.session.commit()
            flash('Lançamento atual removido. O plano continua ativo para os próximos meses.', 'info')
            return redirect(url_for('finance.dashboard', month=trans.date.month, year=trans.date.year))

    if trans.card_id and trans.type == 'despesa':
        if TransactionService.has_invoice_payment(current_user.id, trans.card_id, trans.date):
            flash('Não é possível excluir: fatura já paga.', 'danger')
            return redirect(url_for('finance.dashboard', month=trans.date.month, year=trans.date.year))
            
    if trans.account_id and trans.type == 'despesa' and trans.description.startswith('Pagamento Fatura '):
        card_name = trans.description[17:] 
        card = CreditCard.query.filter_by(user_id=current_user.id, name=card_name).first()
        if card:
            card_payment = Transaction.query.filter_by(
                user_id=current_user.id, card_id=card.id, type='pagamento_cartao',
                date=trans.date, amount=trans.amount
            ).first()
            if card_payment: db.session.delete(card_payment)
    elif trans.card_id and trans.type == 'pagamento_cartao':
        card = CreditCard.query.get(trans.card_id)
        if card:
            bank_payment = Transaction.query.filter(
                Transaction.user_id == current_user.id, type='despesa',
                description=f"Pagamento Fatura {card.name}",
                date=trans.date, amount=trans.amount
            ).first()
            if bank_payment:
                acc = BankAccount.query.get(bank_payment.account_id)
                acc.current_balance += bank_payment.amount
                db.session.delete(bank_payment)

    if trans.account_id:
        account = BankAccount.query.get(trans.account_id)
        if trans.type == 'receita' or trans.type == 'transf_entrada': account.current_balance -= trans.amount
        elif trans.type == 'despesa' or trans.type == 'transf_saida': account.current_balance += trans.amount
    
    db.session.delete(trans)
    db.session.commit()
    return redirect(url_for('finance.dashboard', month=trans.date.month, year=trans.date.year))

@finance_bp.route('/transaction/anticipate_fixed/<int:id>')
@login_required
def anticipate_fixed(id):
    today = date.today()
    trans = Transaction.query.get_or_404(id)
    
    target_date = today
    flash_msg = 'Despesa antecipada para a fatura atual!'

    if trans.card_id:
        trans.description = f"Adiantamento {trans.description}"
    else:
        original_ref = f"(Ref: {trans.date.strftime('%m/%Y')})"
        trans.description = f"Adiantamento {trans.description} {original_ref}"
    
    trans.date = target_date
    
    db.session.commit()
    flash(flash_msg, 'success')
    return redirect(url_for('finance.dashboard'))

@finance_bp.route('/transaction/undo_anticipate/<int:id>')
@login_required
def undo_anticipate(id):
    trans = Transaction.query.get_or_404(id)
    match = re.search(r'Ref: (\d{2})/(\d{4})', trans.description)
    
    if match:
        original_month = int(match.group(1))
        original_year = int(match.group(2))
    elif trans.fixed_expense_id:
        flash('Não foi possível identificar a data original automaticamente para este item de cartão.', 'warning')
        return redirect(url_for('finance.dashboard'))
    else:
        original_month = None
        original_year = None

    if original_month and original_year:
        fixed = FixedExpense.query.get(trans.fixed_expense_id)
        if fixed:
            target_day = fixed.day_of_month
            restored_date = TransactionService.get_safe_date(original_year, original_month, target_day)
            trans.date = restored_date
            trans.description = fixed.description 
            db.session.commit()
            flash('Antecipação desfeita!', 'info')
        else:
            flash('Erro ao encontrar regra original.', 'danger')
    
    return redirect(url_for('finance.dashboard'))

@finance_bp.route('/transaction/edit/<int:id>', methods=['POST'])
@login_required
def edit_transaction(id):
    trans = Transaction.query.get_or_404(id)

    if trans.type in ['transf_saida', 'transf_entrada']:
        trans.description = request.form.get('description')
        db.session.commit()
        return redirect(url_for('finance.dashboard', month=trans.date.month, year=trans.date.year))

    old_amount = trans.amount
    new_amount = Decimal(request.form.get('amount', '0').replace(',', '.'))
    trans.description = request.form.get('description')
    
    if trans.account_id and old_amount != new_amount:
        account = BankAccount.query.get(trans.account_id)
        diff = new_amount - old_amount
        if trans.type == 'receita': account.current_balance += diff
        else: account.current_balance -= diff
    
    trans.amount = new_amount
    db.session.commit()
    return redirect(url_for('finance.dashboard', month=trans.date.month, year=trans.date.year))

@finance_bp.route('/transfer', methods=['POST'])
@login_required
def transfer_values():
    source_id = int(request.form.get('source_id'))
    target_id = int(request.form.get('target_id'))
    amount = Decimal(request.form.get('amount', '0').replace(',', '.'))
    date_str = request.form.get('date')
    date_trans = datetime.strptime(date_str, '%Y-%m-%d').date()
    
    if current_user.start_date:
        start_month = current_user.start_date.replace(day=1)
        if date_trans.replace(day=1) < start_month:
            flash('Data anterior ao início do uso do sistema.', 'danger')
            return redirect(url_for('finance.dashboard'))
    
    success, msg = TransactionService.transfer_funds(current_user.id, source_id, target_id, amount, date_trans)
    if success: flash(msg, 'success')
    else: flash(msg, 'danger')
    return redirect(url_for('finance.dashboard'))

@finance_bp.route('/card/pay', methods=['POST'])
@login_required
def pay_card_invoice():
    card_id = int(request.form.get('card_id'))
    account_id = int(request.form.get('account_id'))
    amount = Decimal(request.form.get('amount', '0').replace(',', '.'))
    date_str = request.form.get('date')
    date_pay = datetime.strptime(date_str, '%Y-%m-%d').date()
    
    if current_user.start_date:
        start_month = current_user.start_date.replace(day=1)
        if date_pay.replace(day=1) < start_month:
            flash('Data anterior ao início do uso do sistema.', 'danger')
            return redirect(url_for('finance.dashboard'))
    
    success, msg = TransactionService.pay_invoice(current_user.id, card_id, account_id, amount, date_pay)
    
    if success: flash(msg, 'success')
    else: flash(msg, 'danger')
        
    return redirect(url_for('finance.dashboard'))

@finance_bp.route('/api/card/<int:card_id>/installments')
@login_required
def get_card_installments(card_id):
    installments = TransactionService.get_future_installments(current_user.id, card_id)
    grouped = {}
    for t in installments:
        key = t.installment_identifier if t.installment_identifier else t.description
        if key not in grouped:
            clean_desc = t.description.split('(')[0].strip()
            grouped[key] = {'identifier': key, 'description': clean_desc, 'count': 0, 'total_remaining': 0.0, 'items': []}
        grouped[key]['count'] += 1
        grouped[key]['total_remaining'] += float(t.amount)
        grouped[key]['items'].append({'id': t.id, 'description': t.description, 'amount': float(t.amount), 'date': t.date.strftime('%d/%m/%Y'), 'current': t.installment_current, 'total': t.installment_total})
    return jsonify(list(grouped.values()))

@finance_bp.route('/card/advance', methods=['POST'])
@login_required
def advance_card_installments():
    card_id = int(request.form.get('card_id'))
    transaction_ids = request.form.getlist('installments[]')
    
    today = date.today()
    success, msg = TransactionService.advance_specific_installments(current_user.id, transaction_ids, today)
    if success: flash(msg, 'info')
    else: flash(msg, 'warning')
        
    return redirect(url_for('finance.dashboard'))

@finance_bp.route('/toggle_fixed/<string:type_fixed>/<int:id>')
@login_required
def toggle_fixed(type_fixed, id):
    today = date.today()
    try:
        target_month = int(request.args.get('month', today.month))
        target_year = int(request.args.get('year', today.year))
    except ValueError:
        target_month = today.month
        target_year = today.year
    
    view_date = date(target_year, target_month, 1)
    current_view_date = today.replace(day=1)
    
    if view_date > current_view_date:
        final_date = today 
        ref_desc = f" (Ref: {target_month:02d}/{target_year})"
        flash_msg = f"Antecipado para hoje com referência a {target_month:02d}/{target_year}."
    else:
        final_date = None 
        ref_desc = ""
        flash_msg = None

    if type_fixed == 'expense':
        fixed_item = FixedExpense.query.get_or_404(id)
        if fixed_item.card_id:
             flash('Despesas fixas de cartão são automáticas.', 'info')
             return redirect(url_for('finance.dashboard', month=target_month, year=target_year))

        existing_trans = Transaction.query.filter(
            Transaction.user_id == current_user.id,
            Transaction.fixed_expense_id == fixed_item.id,
            or_(
                and_(
                    extract('month', Transaction.date) == target_month,
                    extract('year', Transaction.date) == target_year
                ),
                Transaction.description.like(f"%Ref: {target_month:02d}/{target_year}%")
            )
        ).first()
        
        if existing_trans:
            if existing_trans.account_id:
                account = BankAccount.query.get(existing_trans.account_id)
                account.current_balance += existing_trans.amount 
            db.session.delete(existing_trans)
        else:
            if not final_date:
                final_date = TransactionService.get_safe_date(target_year, target_month, fixed_item.day_of_month)

            if fixed_item.account_id:
                account = BankAccount.query.get(fixed_item.account_id)
                if account.current_balance < fixed_item.amount:
                    flash(f'Saldo insuficiente na conta {account.name}.', 'danger')
                    return redirect(url_for('finance.dashboard', month=target_month, year=target_year))

                new_trans = Transaction(
                    user_id=current_user.id, 
                    category_id=fixed_item.category_id, 
                    account_id=fixed_item.account_id,
                    description=fixed_item.description + ref_desc, 
                    amount=fixed_item.amount, 
                    date=final_date, 
                    type='despesa', 
                    fixed_expense_id=fixed_item.id
                )
                account.current_balance -= fixed_item.amount
                db.session.add(new_trans)
                if flash_msg: flash(flash_msg, 'info')
                
    elif type_fixed == 'revenue':
        fixed_item = FixedRevenue.query.get_or_404(id)
        
        existing_trans = Transaction.query.filter(
            Transaction.user_id == current_user.id,
            Transaction.fixed_revenue_id == fixed_item.id,
            or_(
                and_(
                    extract('month', Transaction.date) == target_month,
                    extract('year', Transaction.date) == target_year
                ),
                Transaction.description.like(f"%Ref: {target_month:02d}/{target_year}%")
            )
        ).first()
        
        if fixed_item.account_id:
            account = BankAccount.query.get(fixed_item.account_id)
            if existing_trans:
                account.current_balance -= existing_trans.amount
                db.session.delete(existing_trans)
            else:
                if not final_date:
                    final_date = TransactionService.get_safe_date(target_year, target_month, fixed_item.day_of_month)

                new_trans = Transaction(
                    user_id=current_user.id, category_id=fixed_item.category_id, account_id=fixed_item.account_id,
                    description=fixed_item.description + ref_desc, amount=fixed_item.amount, 
                    date=final_date, type='receita', 
                    fixed_revenue_id=fixed_item.id
                )
                account.current_balance += fixed_item.amount
                db.session.add(new_trans)
                if flash_msg: flash(flash_msg, 'info')
            
    db.session.commit()
    return redirect(url_for('finance.dashboard', month=target_month, year=target_year))