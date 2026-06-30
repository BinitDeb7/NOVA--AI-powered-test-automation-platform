from app import create_app, celery_ext

# Create the Flask application context
app = create_app()

# Expose the Celery application instance for the worker command
celery = celery_ext
