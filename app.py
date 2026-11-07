from app_factory import create_app
from extensions import csrf

__all__ = ['create_app', 'csrf']

if __name__ == '__main__':
    app = create_app()
    # Run locally for development
    app.run(host='127.0.0.1', port=5000, debug=app.config['DEBUG'])
    app.logger.info("Application started on port 5000.")
