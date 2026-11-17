"""Django settings for Pond, a desktop app.

Django runs inside the app (see desktop.py) and only listens on 127.0.0.1.
There is one local user; everything else is configured from the Settings screen.
"""
import os
from pathlib import Path

from .paths import data_dir, secret_key

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = data_dir()

SITE_NAME = "Pond"
SECRET_KEY = os.getenv("SECRET_KEY") or secret_key(DATA_DIR)
DEBUG = os.getenv("POND_DEBUG") == "1"
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]

# The window opens /desktop/start/?token=... with this per-launch token; nothing else can log in.
DESKTOP_TOKEN = os.getenv("POND_TOKEN", "")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "users",
    "bot",
    "guides",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "bot.desktop.DesktopMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "bot.context.site",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DATA_DIR / "pond.sqlite3",
        # the web server and the bot write from different threads: take the write lock at the start of a
        # transaction (IMMEDIATE) and wait for it, instead of failing halfway with "database is locked"
        "OPTIONS": {"timeout": 20, "init_command": "PRAGMA journal_mode=WAL;", "transaction_mode": "IMMEDIATE"},
    }
}

AUTH_USER_MODEL = "users.User"
LOGIN_URL = "/"

LANGUAGE_CODE = "en-us"
USE_I18N = True
USE_TZ = True
try:  # show times in the computer's own time zone
    from tzlocal import get_localzone_name

    TIME_ZONE = get_localzone_name() or "UTC"
except Exception:
    TIME_ZONE = "UTC"

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Demo mode: starting balance in the network's coin and the swap fee (same as Uniswap V2).
PAPER_START_BALANCE = "1"
PAPER_FEE = "0.003"

# Live mode: default cap for a single buy, in the network's coin. Changed in Settings.
LIVE_MAX_TRADE_NATIVE = "0.02"
