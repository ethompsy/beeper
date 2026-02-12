"""Configuration for Beeper UI."""

import os
import secrets


class Config:
    """Base configuration."""

    # Flask settings - use environment variable or generate random key for dev
    SECRET_KEY = os.environ.get("SECRET_KEY", secrets.token_hex(32))
    DEBUG = False
    TESTING = False

    # Operator API settings
    OPERATOR_URL = os.environ.get("BEEPER_OPERATOR_URL", "http://localhost:8080")
    OPERATOR_TIMEOUT = float(os.environ.get("BEEPER_OPERATOR_TIMEOUT", "5.0"))

    # UI settings
    UI_PORT = int(os.environ.get("BEEPER_UI_PORT", "5000"))
    UI_HOST = os.environ.get("BEEPER_UI_HOST", "0.0.0.0")


class DevelopmentConfig(Config):
    """Development configuration."""

    DEBUG = True


class TestingConfig(Config):
    """Testing configuration."""

    TESTING = True
    DEBUG = True
    SECRET_KEY = "test-secret-key-not-for-production"
    # Use mock operator for tests
    OPERATOR_URL = "http://mock-operator:8080"


class ProductionConfig(Config):
    """Production configuration."""

    DEBUG = False

    def __init__(self) -> None:
        """Validate production configuration."""
        if not os.environ.get("SECRET_KEY"):
            raise ValueError(
                "SECRET_KEY environment variable must be set in production. "
                "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
            )


def get_config() -> type[Config]:
    """Get configuration based on environment."""
    env = os.environ.get("FLASK_ENV", "development")
    configs = {
        "development": DevelopmentConfig,
        "testing": TestingConfig,
        "production": ProductionConfig,
    }
    return configs.get(env, DevelopmentConfig)
