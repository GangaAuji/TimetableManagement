"""Select a config class. APP_ENV wins, then FLASK_ENV. Defaults to development.

The environment classes do not override settings. Values still come from the
same environment variables as before.
"""

import os

from config.development import DevelopmentConfig
from config.production import ProductionConfig
from config.testing import TestingConfig

_CONFIGS = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
}


def get_config():
    name = (os.environ.get('APP_ENV') or os.environ.get('FLASK_ENV') or 'development').strip().lower()
    return _CONFIGS.get(name, DevelopmentConfig)


Config = get_config()
