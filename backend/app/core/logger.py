"""Centralized logging configuration for WatchMan.

Provides safe logging utilities that prevent accidental leakage of sensitive
data such as passwords, tokens, API keys, and secret credentials.
"""

import logging
import sys
from typing import Any

SENSITIVE_KEYS = {
    "authorization",
    "password",
    "secret_key",
    "secret",
    "token",
    "access_token",
    "refresh_token",
    "api_key",
    "tmdb_api_key",
    "supabase_anon_key",
    "supabase_service_role_key",
    "postgres_password",
}


def sanitize_data(data: Any) -> Any:
    """Recursively mask sensitive values in dicts and lists."""
    if isinstance(data, dict):
        sanitized = {}
        for k, v in data.items():
            if str(k).lower() in SENSITIVE_KEYS:
                sanitized[k] = "******"
            else:
                sanitized[k] = sanitize_data(v)
        return sanitized
    if isinstance(data, list):
        return [sanitize_data(item) for item in data]
    return data


def setup_logger(name: str = "watchman") -> logging.Logger:
    """Get or configure the application logger."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.propagate = False
    return logger


logger = setup_logger()
