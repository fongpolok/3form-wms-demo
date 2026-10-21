from pathlib import Path
import os

from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

from core import config as threeform_config  # noqa: E402  (needs .env loaded first)
from core.logging_setup import build_logging  # noqa: E402

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY') or os.environ['SECRET_KEY']

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get('DJANGO_DEBUG', 'False') == 'True'

ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', '127.0.0.1,localhost').split(',')
# Render tells the app its own public address; accept it without a manual setting.
if os.environ.get('RENDER_EXTERNAL_HOSTNAME'):
    ALLOWED_HOSTS.append(os.environ['RENDER_EXTERNAL_HOSTNAME'])

# Behind the Caddy HTTPS proxy (edge box / cloud): trust its X-Forwarded-Proto header.
if os.environ.get('DJANGO_BEHIND_PROXY') == 'True':
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'
    CSRF_TRUSTED_ORIGINS = [o for o in os.environ.get('CSRF_TRUSTED_ORIGINS', '').split(',') if o]
    if os.environ.get('RENDER_EXTERNAL_HOSTNAME'):
        CSRF_TRUSTED_ORIGINS.append('https://' + os.environ['RENDER_EXTERNAL_HOSTNAME'])


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'staff.apps.StaffConfig',
    'userprofile.apps.UserprofileConfig',
    'userregister.apps.UserregisterConfig',
    'userlogin.apps.UserloginConfig',
    'company.apps.CompanyConfig',
    'supplier.apps.SupplierConfig',
    'asn.apps.AsnConfig',
    'dn.apps.DnConfig',
    'binset.apps.BinsetConfig',
    'binsize.apps.BinsizeConfig',
    'binproperty.apps.BinpropertyConfig',
    'customer.apps.CustomerConfig',
    'capital.apps.CapitalConfig',
    'cyclecount.apps.CyclecountConfig',
    'dashboard.apps.DashboardConfig',
    'warehouse.apps.WarehouseConfig',
    'goods.apps.GoodsConfig',
    'goodsunit.apps.GoodsunitConfig',
    'goodsclass.apps.GoodsclassConfig',
    'goodscolor.apps.GoodscolorConfig',
    'goodsbrand.apps.GoodsbrandConfig',
    'goodsshape.apps.GoodsshapeConfig',
    'goodsspecs.apps.GoodsspecsConfig',
    'goodsorigin.apps.GoodsoriginConfig',
    'payment.apps.PaymentConfig',
    'driver.apps.DriverConfig',
    'stock.apps.StockConfig',
    'throttle.apps.ThrottleConfig',
    'uploadfile.apps.UploadfileConfig',
    'scanner.apps.ScannerConfig',
    'core.apps.CoreConfig',
    'accounts.apps.AccountsConfig',
    'mes.apps.MesConfig',
    'reports.apps.ReportsConfig',
    'inventory.apps.InventoryConfig',
    'aps.apps.ApsConfig',
    'integrations.apps.IntegrationsConfig',
    'optimiser.apps.OptimiserConfig',
    'agent.apps.AgentConfig',
    'rest_framework',
    'django_filters',
    'corsheaders',
    'drf_spectacular',
    'drf_spectacular_sidecar'
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    #'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'core.middleware.LegacyStockReadOnlyMiddleware',
    'core.public_demo.PublicDemoGuardMiddleware',
]

ROOT_URLCONF = 'greaterwms.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'frontend' / 'dist'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'greaterwms.wsgi.application'
CSRF_COOKIE_SAMESITE = None

# Database: PostgreSQL for WMS stock, users and audit trail.
# MES / production events live in MongoDB (see core/mongo.py).
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'HOST': os.environ.get('POSTGRES_HOST', '127.0.0.1'),
        'PORT': os.environ.get('POSTGRES_PORT', '5433'),
        'NAME': os.environ.get('POSTGRES_DB', 'threeform_wms'),
        'USER': os.environ.get('POSTGRES_USER', 'threeform'),
        'PASSWORD': os.environ.get('POSTGRES_PASSWORD', ''),
        'CONN_MAX_AGE': 60,
        # Hosted databases (e.g. Neon for the public demo) need an encrypted connection: POSTGRES_SSLMODE=require
        'OPTIONS': {'sslmode': os.environ['POSTGRES_SSLMODE']} if os.environ.get('POSTGRES_SSLMODE') else {},
    }
}
# One-off: read the old SQLite file (used only to copy legacy data into PostgreSQL).
if os.environ.get('LEGACY_SQLITE_PATH'):
    DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': os.environ['LEGACY_SQLITE_PATH']}}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Password validation
# https://docs.djangoproject.com/en/3.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/3.1/topics/i18n/

LANGUAGE_CODE = 'en'

TIME_ZONE = threeform_config.get('site.timezone', 'Asia/Hong_Kong')

USE_I18N = True

USE_TZ = False


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/3.1/howto/static-files/

STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'static_new').replace('\\', '/')
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'static').replace('\\', '/'),
]

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media').replace('\\', '/')

SPECTACULAR_SETTINGS = {
    'TITLE': '3Form WMS / MES / APS',
    'DESCRIPTION': '3Form WMS API (agent-ready). Auth: Authorization: Bearer <token>',
    'VERSION': '3.6.0',
    'SERVE_INCLUDE_SCHEMA': False,
    # OTHER SETTINGS
    'SWAGGER_UI_DIST': 'SIDECAR',  # shorthand to use the sidecar instead
    'SWAGGER_UI_FAVICON_HREF': 'SIDECAR',
    'REDOC_DIST': 'SIDECAR',
    # OTHER SETTINGS
}

REST_FRAMEWORK = {
    # AttributeError: ‘AutoSchema’ object has no attribute ‘get_link’
    # DEFAULT SET:
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    # 'DEFAULT_SCHEMA_CLASS': 'rest_framework.schemas.openapi.AutoSchema',
    # EXCEPTION:
    'EXCEPTION_HANDLER': 'utils.my_exceptions.custom_exception_handler',
    # Base API policies:
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
        'rest_framework_csv.renderers.CSVRenderer',
        #'rest_framework.renderers.BrowsableAPIRenderer',
    ],
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
        'rest_framework.parsers.FormParser',
        'rest_framework.parsers.MultiPartParser'
    ],
    # Per-person expiring tokens. Default: only PIC / Eng. Manager may call an
    # endpoint; worker endpoints opt in explicitly (secure by default).
    'DEFAULT_AUTHENTICATION_CLASSES': ['accounts.authentication.TokenAuthentication', ],
    'DEFAULT_PERMISSION_CLASSES': ["accounts.permissions.IsManagerOrAbove", ],
    'DEFAULT_THROTTLE_CLASSES': ['rest_framework.throttling.UserRateThrottle',
                                 'rest_framework.throttling.AnonRateThrottle'],
    'DEFAULT_THROTTLE_RATES': {'user': threeform_config.get('api.throttle_user', '1200/min'),
                               'anon': threeform_config.get('api.throttle_anon', '3000/min')},
    'DEFAULT_CONTENT_NEGOTIATION_CLASS': 'rest_framework.negotiation.DefaultContentNegotiation',
    'DEFAULT_METADATA_CLASS': 'rest_framework.metadata.SimpleMetadata',
    'DEFAULT_VERSIONING_CLASS': None,
    # 'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    # 'PAGE_SIZE': 1,  # 默认 None
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        # 'django_filters.rest_framework.backends.DjangoFilterBackend',
    ],
    'SEARCH_PARAM': 'search',
    'ORDERING_PARAM': 'ordering',
    'NUM_PROXIES': None,
    # Versioning:
    'DEFAULT_VERSION': None,
    'ALLOWED_VERSIONS': None,
    'VERSION_PARAM': 'version',
    # Authentication:
    'UNAUTHENTICATED_USER': 'django.contrib.auth.models.AnonymousUser',
    'UNAUTHENTICATED_TOKEN': None,
    # View configuration:
    'VIEW_NAME_FUNCTION': 'rest_framework.views.get_view_name',
    'VIEW_DESCRIPTION_FUNCTION': 'rest_framework.views.get_view_description',
    'NON_FIELD_ERRORS_KEY': 'non_field_errors',
    # Testing
    'TEST_REQUEST_RENDERER_CLASSES': [
        'rest_framework.renderers.MultiPartRenderer',
        'rest_framework.renderers.JSONRenderer'
    ],
    'TEST_REQUEST_DEFAULT_FORMAT': 'multipart',
    # Hyperlink settings
    'URL_FORMAT_OVERRIDE': 'format',
    'FORMAT_SUFFIX_KWARG': 'format',
    'URL_FIELD_NAME': 'url',
    # Encoding
    'UNICODE_JSON': True,
    'COMPACT_JSON': True,
    'STRICT_JSON': True,
    'COERCE_DECIMAL_TO_STRING': True,
    'UPLOADED_FILES_USE_URL': True,
    # Browseable API
    'HTML_SELECT_CUTOFF': 1000,
    'HTML_SELECT_CUTOFF_TEXT': "More than {count} items...",
    # Schemas
    'SCHEMA_COERCE_PATH_PK': True,
    'SCHEMA_COERCE_METHOD_NAMES': {
        'retrieve': 'read',
        'destroy': 'delete'
    },
}

# One daily-rotated log file per channel (app, scanner, camera, aps, agent, audit).
LOGGING = build_logging(BASE_DIR)

# Tunable thresholds for the low-stock / expiry alert feature (stock/services.py).
# Change these instead of editing alert logic.
WMS_ALERT_SETTINGS = {
    "EXPIRY_ALERT_DAYS": 90,       # flag a lot as "expiring soon" within this many days
    "LOW_STOCK_ALERT_ENABLED": True,
    "EXPIRY_ALERT_ENABLED": True,
}

CORS_ALLOW_CREDENTIALS = False
CORS_ALLOWED_ORIGINS = [o for o in os.environ.get('CORS_ALLOWED_ORIGINS', 'http://localhost:5173,http://127.0.0.1:5173').split(',') if o]

CORS_ALLOW_METHODS = (
    'DELETE',
    'GET',
    'OPTIONS',
    'PATCH',
    'POST',
    'PUT',
    'VIEW',
)

CORS_ALLOW_HEADERS = (
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
    'token',
    'language',
    'operator',
    'device',
    'app-id',
    'event-sign',
    'x-device-token',
    'x-gateway-token',
)

LAZY_RENDERING = True
NATIVE_SCROLLBARS = True

ALLOCATION_SECONDS = 1
GET_THROTTLE = 500
POST_THROTTLE = 500
PUT_THROTTLE = 500
PATCH_THROTTLE = 500
DELETE_THROTTLE = 500

JWT_TIME = 60 * 60 * 24 * 365 * 20  # legacy GreaterWMS, unused by new auth
