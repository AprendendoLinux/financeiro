from flask import Flask, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, current_user
from .config import Config 

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Inicializa as extensões
    db.init_app(app)
    migrate.init_app(app, db)
    
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    
    # Remove a mensagem padrão de "Faça login para acessar"
    login_manager.login_message = '' 

    # Importação dos Models
    from . import models 

    @login_manager.user_loader
    def load_user(user_id):
        if user_id is not None:
            return models.User.query.get(int(user_id))
        return None

    # Registro dos Blueprints
    from .auth_controller import auth_bp
    app.register_blueprint(auth_bp)

    from .finance_controller import finance_bp
    app.register_blueprint(finance_bp)

    from .settings_controller import settings_bp
    app.register_blueprint(settings_bp)
    
    @app.route('/health')
    def health_check():
        return {'status': 'healthy', 'db': 'connected'}, 200

    # --- CORREÇÃO DO ERRO 404 NA RAIZ ---
    @app.route('/')
    def index():
        # Se já estiver logado, vai pro dashboard
        if current_user.is_authenticated:
            return redirect(url_for('finance.dashboard'))
        # Se não, manda pro login
        return redirect(url_for('auth.login'))
    # ------------------------------------

    return app