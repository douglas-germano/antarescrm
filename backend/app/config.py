import os
import json
from pathlib import Path
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()


def normalize_database_url(value):
    for prefix in ('postgres://', 'postgresql://'):
        if value.startswith(prefix):
            return 'postgresql+psycopg://' + value[len(prefix):]
    return value


class Config:
    BACKUP_STATUS_PATH = os.getenv('BACKUP_STATUS_PATH', str(Path.home()/'.antarescrm-deploy-backups/automatic/latest.json'))
    SQLALCHEMY_DATABASE_URI = normalize_database_url(os.getenv('DATABASE_URL', 'postgresql+psycopg:///antarescrm'))
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {'pool_pre_ping': True}
    SECRET_KEY = os.getenv('SECRET_KEY', 'development-only-change-this-secret')
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'development-only-change-this-jwt-secret')
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=30)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=7)
    JWT_TOKEN_LOCATION = ['headers']
    ALLOWED_ORIGINS = [x.strip() for x in os.getenv('ALLOWED_ORIGINS', 'http://localhost:3000').split(',') if x.strip()]
    ALLOW_REGISTRATION = os.getenv('ALLOW_REGISTRATION', 'true').lower() == 'true'
    RATELIMIT_STORAGE_URI = os.getenv('RATELIMIT_STORAGE_URI', 'memory://')
    JSON_SORT_KEYS = False
    COMMUNICATION_ACCOUNTS = json.loads(os.getenv('COMMUNICATION_ACCOUNTS', '{}'))
    # WhatsApp — Evolution API (one instance per workspace, one server for all)
    EVOLUTION_API_URL = os.getenv('EVOLUTION_API_URL')
    EVOLUTION_API_KEY = os.getenv('EVOLUTION_API_KEY')
    WHATSAPP_WEBHOOK_BASE_URL = os.getenv('WHATSAPP_WEBHOOK_BASE_URL')
    WHATSAPP_WEBHOOK_SECRET = os.getenv('WHATSAPP_WEBHOOK_SECRET')
    WHATSAPP_MEDIA_MAX_BYTES = 10 * 1024 * 1024
    PROJECT_FILES_DIR = os.getenv('PROJECT_FILES_DIR', str(Path(__file__).resolve().parents[2] / '.local-services' / 'project-files'))
    PROJECT_FILE_MAX_BYTES = 14 * 1024 * 1024  # stays under the request limit
    MAX_CONTENT_LENGTH = 15 * 1024 * 1024
    INSTAGRAM_APP_ID = os.getenv('INSTAGRAM_APP_ID')
    INSTAGRAM_APP_SECRET = os.getenv('INSTAGRAM_APP_SECRET')
    INSTAGRAM_ENCRYPTION_KEY = os.getenv('INSTAGRAM_ENCRYPTION_KEY')
    INSTAGRAM_REDIRECT_URI = os.getenv('INSTAGRAM_REDIRECT_URI', 'https://antares.douglasgermano.com/api/v1/instagram/callback')
    INSTAGRAM_API_VERSION = os.getenv('INSTAGRAM_API_VERSION', 'v25.0')


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = normalize_database_url(os.getenv('TEST_DATABASE_URL', 'sqlite:///:memory:'))
    SQLALCHEMY_ENGINE_OPTIONS = {}
    RATELIMIT_ENABLED = False
    ALLOW_REGISTRATION = True
    EVOLUTION_API_URL = None
    EVOLUTION_API_KEY = None
    WHATSAPP_WEBHOOK_BASE_URL = None
    WHATSAPP_WEBHOOK_SECRET = None
