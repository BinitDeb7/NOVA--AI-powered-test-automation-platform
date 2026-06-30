from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_compress import Compress
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from celery import Celery

db      = SQLAlchemy()
limiter = Limiter(key_func=get_remote_address, default_limits=[])
compress = Compress()
celery_ext = Celery(__name__)
migrate = Migrate()
csrf = CSRFProtect()

def create_app(config_name: str = 'default') -> Flask:
    app = Flask(__name__)

    # Load config from config.py
    from config import config
    app.config.from_object(config[config_name])

    # Initialize Celery
    celery_ext.conf.update(
        broker_url=app.config.get('CELERY_BROKER_URL', 'redis://localhost:6379/0'),
        result_backend=app.config.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0'),
        task_always_eager=app.config.get('CELERY_TASK_ALWAYS_EAGER', False),
        task_eager_propagates=app.config.get('CELERY_TASK_EAGER_PROPAGATES', False),
        task_store_eager_result=app.config.get('CELERY_TASK_STORE_EAGER_RESULT', False),
    )
    class ContextTask(celery_ext.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)
    celery_ext.Task = ContextTask

    # Extensions
    db.init_app(app)
    limiter.init_app(app)
    compress.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)

    # Auth
    login_manager = LoginManager()
    login_manager.login_view = 'auth.login'
    login_manager.init_app(app)

    from app.models import User
    @login_manager.user_loader
    def load_user(user_id: str):
        return User.query.get(int(user_id))

    # Blueprints
    from app.routes import register_blueprints
    register_blueprints(app)

    # Exempt standard views and authentication forms from CSRF Protect
    from app.routes.auth import auth_bp
    from app.routes.main import main_bp
    csrf.exempt(auth_bp)
    csrf.exempt(main_bp)

    # Error handlers
    from flask_wtf.csrf import CSRFError
    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        from flask import jsonify
        return jsonify({"success": False, "error": f"CSRF validation failed: {e.description}"}), 400

    @app.errorhandler(404)
    def not_found(e):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template('errors/500.html'), 500

    # Create DB tables if they don't exist
    with app.app_context():
        if app.config['SQLALCHEMY_DATABASE_URI'].startswith('sqlite'):
            from sqlalchemy import text
            db.session.execute(text('PRAGMA journal_mode=WAL;'))
            db.session.execute(text('PRAGMA synchronous=NORMAL;'))
            db.session.commit()
        db.create_all()

    return app
