from app import create_app

app = create_app()

# --- FILTROS JINJA2 PERSONALIZADOS ---

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

def trim_slash(value):
    """
    Remove a barra final de uma string, útil para construir URLs absolutas de imagens.
    """
    return value.rstrip('/')

# Registra os filtros diretamente na instância do app criada
app.jinja_env.filters['currency'] = format_currency
app.jinja_env.filters['trim_slash'] = trim_slash
# -----------------------------------

if __name__ == '__main__':
    # Alterado para '::' para suportar IPv6 (e IPv4 em dual-stack)
    app.run(host='::', port=5000)