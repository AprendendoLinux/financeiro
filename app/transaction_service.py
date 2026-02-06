from app import db
from app.models import Transaction, CreditCard, BankAccount, User, Category
from sqlalchemy import func, extract, and_, or_
from datetime import date, datetime, timedelta
from dateutil.relativedelta import relativedelta
import calendar

class TransactionService:
    
    @staticmethod
    def get_safe_date(year, month, day):
        last_day = calendar.monthrange(year, month)[1]
        return date(year, month, min(day, last_day))

    @staticmethod
    def calculate_card_date(purchase_date, card):
        return purchase_date

    @staticmethod
    def get_invoice_dates(card, ref_month, ref_year):
        closing_date = TransactionService.get_safe_date(ref_year, ref_month, card.closing_day)
        previous_closing = closing_date - relativedelta(months=1)
        opening_date = previous_closing + timedelta(days=1)
        
        if card.due_day <= card.closing_day:
            due_date_pre = closing_date + relativedelta(months=1)
            due_date = TransactionService.get_safe_date(due_date_pre.year, due_date_pre.month, card.due_day)
        else:
            due_date = TransactionService.get_safe_date(ref_year, ref_month, card.due_day)
            
        return opening_date, closing_date, due_date

    @staticmethod
    def get_card_stats(user_id, card_id, month, year):
        card = CreditCard.query.get(card_id)
        today = date.today()

        open_date, close_date, due_date = TransactionService.get_invoice_dates(card, month, year)
        
        # 1. Total da Fatura
        invoice_expenses = db.session.query(func.sum(Transaction.amount)).filter(
            Transaction.card_id == card_id,
            Transaction.type == 'despesa',
            Transaction.date >= open_date,
            Transaction.date <= close_date,
            or_(
                Transaction.fixed_expense_id == None,
                Transaction.date <= today
            )
        ).scalar() or 0
        
        # 2. Pagamentos efetuados
        invoice_payments = db.session.query(func.sum(Transaction.amount)).filter(
            Transaction.card_id == card_id,
            Transaction.type == 'pagamento_cartao',
            Transaction.date >= open_date,
            Transaction.date <= (due_date + timedelta(days=20)) 
        ).scalar() or 0
        
        current_invoice = float(invoice_expenses) - float(invoice_payments)

        # 3. Limite Global
        total_spent = db.session.query(func.sum(Transaction.amount))\
            .filter(
                Transaction.card_id == card_id, 
                Transaction.type == 'despesa',
                or_(
                    Transaction.date <= today,
                    Transaction.fixed_expense_id == None
                )
            )\
            .scalar() or 0
            
        total_paid = db.session.query(func.sum(Transaction.amount))\
            .filter(
                Transaction.card_id == card_id, 
                Transaction.type == 'pagamento_cartao'
            )\
            .scalar() or 0
            
        used_limit = total_spent - total_paid
        available = float(card.limit_amount) - float(used_limit)
        
        percent = 0
        if card.limit_amount > 0:
            percent = (float(used_limit) / float(card.limit_amount)) * 100

        is_paid = current_invoice <= 0.01

        return {
            'obj': card,
            'limit': card.limit_amount,
            'used': used_limit,
            'available': available,
            'percent': min(percent, 100),
            'invoice_amount': max(current_invoice, 0),
            'is_paid': is_paid,
            'full_due_date': due_date.strftime('%d/%m/%Y'),
            'full_closing_date': close_date.strftime('%d/%m/%Y'),
            'target_month': due_date.month,
            'target_year': due_date.year
        }

    @staticmethod
    def check_card_limit(user_id, card_id, amount):
        today = date.today()
        stats = TransactionService.get_card_stats(user_id, card_id, today.month, today.year)
        
        if float(amount) > stats['available']:
            return False, f"Limite insuficiente. Disponível: R$ {stats['available']:.2f}"
        return True, "OK"
    
    @staticmethod
    def pay_invoice(user_id, card_id, account_id, amount, date_payment):
        card = CreditCard.query.get(card_id)
        account = BankAccount.query.get(account_id)
        
        if account.current_balance < amount:
            return False, f"Saldo insuficiente em {account.name}."
        
        account.current_balance -= amount
        
        # --- Lógica da Categoria Pagamento ---
        # Busca ou cria a categoria de sistema "Pagamento" (Vermelha)
        pay_cat = Category.query.filter_by(user_id=user_id, type='pagamento').first()
        if not pay_cat:
            pay_cat = Category(
                user_id=user_id, 
                name='Pagamento', 
                type='pagamento', # Tipo especial
                color_hex='#EF4444'   # Vermelho
            )
            db.session.add(pay_cat)
            db.session.flush()

        t_bank = Transaction(
            user_id=user_id, account_id=account.id,
            description=f"Pagamento Fatura {card.name}",
            amount=amount, date=date_payment, type='despesa',
            category_id=pay_cat.id
        )
        db.session.add(t_bank)
        
        t_card = Transaction(
            user_id=user_id, card_id=card.id,
            description=f"Pagamento Recebido",
            amount=amount, date=date_payment, type='pagamento_cartao' 
        )
        db.session.add(t_card)
        
        card.last_paid_date = date_payment
        db.session.commit()
        return True, "Pagamento registrado com sucesso!"

    @staticmethod
    def get_future_installments(user_id, card_id):
        today = date.today()
        installments = Transaction.query.filter(
            Transaction.user_id == user_id,
            Transaction.card_id == card_id,
            Transaction.date > today,
            Transaction.type == 'despesa',
            Transaction.installment_total > 1
        ).order_by(Transaction.date.asc()).all()
        return installments

    @staticmethod
    def advance_specific_installments(user_id, transaction_ids, advance_date=None):
        if not transaction_ids: return False, "Nada selecionado."
        
        target_date = advance_date if advance_date else date.today()
        
        count = 0
        for tid in transaction_ids:
            trans = Transaction.query.get(tid)
            if trans and trans.user_id == user_id:
                trans.date = target_date
                if "(Antecipado)" not in trans.description:
                    trans.description = f"{trans.description} (Antecipado)"
                count += 1
        db.session.commit()
        return True, f"{count} parcelas antecipadas."

    @staticmethod
    def transfer_funds(user_id, source_id, target_id, amount, date_trans, description=None):
        if source_id == target_id: return False, "Contas iguais."
        source = BankAccount.query.get(source_id)
        target = BankAccount.query.get(target_id)
        
        if source.current_balance < amount:
            return False, f"Saldo insuficiente em {source.name}."
            
        # --- Lógica da Categoria de Transferência ---
        trans_cat = Category.query.filter_by(user_id=user_id, type='transferencia').first()
        if not trans_cat:
            trans_cat = Category(
                user_id=user_id, 
                name='Transferência', 
                type='transferencia', 
                color_hex='#3B82F6'
            )
            db.session.add(trans_cat)
            db.session.flush()

        t_out = Transaction(
            user_id=user_id, account_id=source.id,
            description=description or f"Transf. para {target.name}",
            amount=amount, date=date_trans, type='transf_saida',
            category_id=trans_cat.id
        )
        t_in = Transaction(
            user_id=user_id, account_id=target.id,
            description=description or f"Recebido de {source.name}",
            amount=amount, date=date_trans, type='transf_entrada',
            category_id=trans_cat.id
        )
        
        source.current_balance -= amount
        target.current_balance += amount
        
        db.session.add(t_out)
        db.session.add(t_in)
        db.session.commit()
        return True, "Transferência realizada."

    @staticmethod
    def has_invoice_payment(user_id, card_id, purchase_date):
        card = CreditCard.query.get(card_id)
        if not card: return False

        if purchase_date.day > card.closing_day:
            ref_date = purchase_date + relativedelta(months=1)
        else:
            ref_date = purchase_date
            
        open_date, close_date, due_date = TransactionService.get_invoice_dates(card, ref_date.month, ref_date.year)

        payment = db.session.query(Transaction).filter(
            Transaction.user_id == user_id,
            Transaction.card_id == card_id,
            Transaction.type == 'pagamento_cartao',
            Transaction.date >= open_date,
            Transaction.date <= (due_date + timedelta(days=10))
        ).first()

        return payment is not None