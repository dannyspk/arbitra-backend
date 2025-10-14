"""Environment configuration and management."""
import os
from enum import Enum

class Environment(Enum):
    """Application environment types."""
    DEVELOPMENT = "development"
    TESTING = "testing"
    STAGING = "staging"
    PRODUCTION = "production"


# Get current environment from env variable
CURRENT_ENV = os.getenv("ENVIRONMENT", "development").lower()

# Parse environment
if CURRENT_ENV in ["prod", "production"]:
    ENV = Environment.PRODUCTION
elif CURRENT_ENV in ["stage", "staging"]:
    ENV = Environment.STAGING
elif CURRENT_ENV in ["test", "testing"]:
    ENV = Environment.TESTING
else:
    ENV = Environment.DEVELOPMENT


def is_production() -> bool:
    """Check if running in production environment."""
    return ENV == Environment.PRODUCTION


def is_staging() -> bool:
    """Check if running in staging environment."""
    return ENV == Environment.STAGING


def is_testing() -> bool:
    """Check if running in testing environment."""
    return ENV == Environment.TESTING


def is_development() -> bool:
    """Check if running in development environment."""
    return ENV == Environment.DEVELOPMENT


def require_production(feature_name: str = "This feature"):
    """Raise error if not in production."""
    if not is_production():
        raise RuntimeError(
            f"{feature_name} is only available in production environment. "
            f"Current environment: {ENV.value}"
        )


def require_non_production(feature_name: str = "This feature"):
    """Raise error if in production."""
    if is_production():
        raise RuntimeError(
            f"{feature_name} is not available in production environment."
        )


# Security settings based on environment
SECURITY_CONFIG = {
    Environment.DEVELOPMENT: {
        "require_auth": False,          # Auth optional in dev
        "require_https": False,         # HTTP allowed in dev
        "enable_rate_limiting": False,  # No rate limits in dev
        "enable_cors": True,            # Wide CORS for dev
        "cors_origins": ["*"],          # All origins allowed
        "enforce_api_keys": False,      # Can use default keys
        "log_level": "DEBUG",           # Verbose logging
        "enable_websocket_auth": False, # WS auth optional
    },
    Environment.TESTING: {
        "require_auth": False,          # Auth optional for tests
        "require_https": False,         # HTTP for tests
        "enable_rate_limiting": False,  # No rate limits in tests
        "enable_cors": True,            # Allow test requests
        "cors_origins": ["*"],          # All origins for tests
        "enforce_api_keys": False,      # Test keys allowed
        "log_level": "INFO",            # Normal logging
        "enable_websocket_auth": False, # WS auth optional
    },
    Environment.STAGING: {
        "require_auth": True,           # Auth required
        "require_https": True,          # HTTPS only
        "enable_rate_limiting": True,   # Rate limiting enabled
        "enable_cors": True,            # Specific origins
        "cors_origins": [               # Staging frontend URLs
            "http://localhost:3000",
            "https://staging.arbitra.com"
        ],
        "enforce_api_keys": True,       # Real API keys required
        "log_level": "INFO",            # Normal logging
        "enable_websocket_auth": True,  # WS auth required
    },
    Environment.PRODUCTION: {
        "require_auth": True,           # Auth REQUIRED
        "require_https": True,          # HTTPS ONLY
        "enable_rate_limiting": True,   # Rate limiting ENABLED
        "enable_cors": True,            # Strict origins
        "cors_origins": [               # Production URLs only
            "https://arbitra.com",
            "https://www.arbitra.com",
            "https://app.arbitra.com"
        ],
        "enforce_api_keys": True,       # Real API keys REQUIRED
        "log_level": "WARNING",         # Minimal logging
        "enable_websocket_auth": True,  # WS auth REQUIRED
    }
}


def get_security_config() -> dict:
    """Get security configuration for current environment."""
    return SECURITY_CONFIG[ENV]


def get_config(key: str, default=None):
    """Get specific security config value."""
    return get_security_config().get(key, default)


# CORS origins for current environment
def get_cors_origins() -> list:
    """Get allowed CORS origins for current environment."""
    return get_config("cors_origins", ["*"])


# Database paths based on environment
def get_database_path(db_name: str = "security.db") -> str:
    """Get database path for current environment."""
    if is_production():
        return f"data/prod/{db_name}"
    elif is_staging():
        return f"data/staging/{db_name}"
    elif is_testing():
        return f"data/test/{db_name}"
    else:
        return f"data/dev/{db_name}"


# API URL based on environment
def get_api_url() -> str:
    """Get API base URL for current environment."""
    if is_production():
        return os.getenv("PROD_API_URL", "https://api.arbitra.com")
    elif is_staging():
        return os.getenv("STAGING_API_URL", "https://staging-api.arbitra.com")
    else:
        return os.getenv("DEV_API_URL", "http://localhost:8000")


# Print current environment on module load
print(f"🌍 Environment: {ENV.value.upper()}")
print(f"🔒 Security Config:")
config = get_security_config()
for key, value in config.items():
    print(f"   - {key}: {value}")
