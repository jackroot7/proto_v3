import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = 'proto-v3-local-secret-change-in-production-xyz789'

DEBUG = True
ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'shops',
    'products',
    'pos',
    'stock',
    'purchases',
    'expenses',
    'staff',
    'customers',
    'reports',
    'sync_engine',
    'settings_app',
    'units',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'shops.context_processors.current_shop',
                'settings_app.context_processors.shop_settings',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'proto_v3.db',
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
]

LANGUAGE_CODE = 'sw'
TIME_ZONE = 'Africa/Dar_es_Salaam'
USE_I18N = True
USE_TZ = True

LANGUAGES = [
    ('sw', 'Kiswahili'),
    ('en', 'English'),
]

LOCALE_PATHS = [BASE_DIR / 'locale']

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/shop-select/'
LOGOUT_REDIRECT_URL = '/login/'

# Proto v3 business settings
PROTO_TAX_RATE = 0.18
PROTO_LOW_STOCK_THRESHOLD = 10
PROTO_CURRENCY = 'TSh'
PROTO_DAILY_REPORT_TIME = '22:00'
PROTO_APP_NAME = 'Proto v3'
PROTO_VERSION = '3.0.0'

# ── Sync Engine ─────────────────────────────────────────────────
# Set these on the local machine to enable cloud sync
CLOUD_SYNC_URL     = os.environ.get('CLOUD_SYNC_URL', 'http://102.223.19.30:8003')          # e.g. https://yourserver.com/sync/receive/
CLOUD_SYNC_API_KEY = os.environ.get('CLOUD_SYNC_API_KEY', 'production-xyz789production-xyz789')      # Secret key shared with cloud server
SYNC_TIMEOUT       = int(os.environ.get('SYNC_TIMEOUT', '15'))     # seconds per request
SYNC_MAX_RETRIES   = int(os.environ.get('SYNC_MAX_RETRIES', '3'))  # max attempts before marking failed
SYNC_BATCH_SIZE    = int(os.environ.get('SYNC_BATCH_SIZE', '50'))  # items per sync batch