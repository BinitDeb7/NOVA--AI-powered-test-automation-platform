import os
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv

load_dotenv(override=False)  # Docker env vars must take precedence over .env


class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'change-me-in-production')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    _db_url = os.getenv('DATABASE_URL', 'sqlite:///database.db')
    # Heroku/Render use postgres:// — SQLAlchemy requires postgresql://
    SQLALCHEMY_DATABASE_URI = (
        _db_url.replace('postgres://', 'postgresql://', 1)
        if _db_url.startswith('postgres://')
        else _db_url
    )

    CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
    CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
    
    # Seamless local execution without Redis/Celery worker process
    CELERY_TASK_ALWAYS_EAGER = os.getenv('CELERY_TASK_ALWAYS_EAGER', 'False').lower() == 'true'
    CELERY_TASK_EAGER_PROPAGATES = True
    CELERY_TASK_STORE_EAGER_RESULT = True

    # DB Engine Options
    if _db_url.startswith('sqlite'):
        SQLALCHEMY_ENGINE_OPTIONS = {
            'connect_args': {'check_same_thread': False, 'timeout': 15}
        }
    else:
        # PostgreSQL: connection pooling for concurrency
        SQLALCHEMY_ENGINE_OPTIONS = {
            'pool_size': 10,
            'max_overflow': 20,
            'pool_pre_ping': True,
            'pool_recycle': 280,
        }


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


config = {
    'development': DevelopmentConfig,
    'production':  ProductionConfig,
    'default':     DevelopmentConfig,
}
