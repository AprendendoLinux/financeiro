from app import create_app

app = create_app()

# --- CORREÇÃO DO FILTRO DE MOEDA ---
def format_currency(value):
    """
    Formata números float/decimal para o padrão BRL (1.500,00)
    """
    try:
        if value is None:
            value = 0.0
        value = float(value)
        # Formata padrão americano (1,500.00)
        formatted = "{:,.2f}".format(value)
        # Troca os separadores: vírgula vira X, ponto vira vírgula, X vira ponto
        return formatted.replace(",", "X").replace(".", ",").replace("X", ".")
    except (ValueError, TypeError):
        return value

# Registra o filtro diretamente na instância do app criada
app.jinja_env.filters['currency'] = format_currency
# -----------------------------------

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)