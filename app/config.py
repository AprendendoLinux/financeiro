import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'sua-chave-secreta-dev'
    
    DB_USER = os.environ.get('DB_USER')
    DB_PASS = os.environ.get('DB_PASSWORD')
    DB_HOST = os.environ.get('DB_HOST')
    DB_NAME = os.environ.get('DB_NAME')
    
    if DB_USER and DB_PASS and DB_HOST and DB_NAME:
        SQLALCHEMY_DATABASE_URI = f"mysql+mysqlconnector://{DB_USER}:{DB_PASS}@{DB_HOST}/{DB_NAME}"
    else:
        SQLALCHEMY_DATABASE_URI = 'sqlite:///local_finance.db'
        
    SQLALCHEMY_TRACK_MODIFICATIONS = False