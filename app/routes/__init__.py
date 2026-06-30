from .main import main_bp
from .auth import auth_bp
from .test_api import test_api_bp
from .export_api import export_bp


def register_blueprints(app):
    app.register_blueprint(auth_bp,     url_prefix='/auth')
    app.register_blueprint(main_bp)
    app.register_blueprint(test_api_bp)
    app.register_blueprint(export_bp)
