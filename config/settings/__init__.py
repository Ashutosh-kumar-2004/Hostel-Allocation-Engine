"""
Settings initialization: Automatically selects development or production settings
based on the ENVIRONMENT environment variable.
"""
import os

ENVIRONMENT = os.environ.get("ENVIRONMENT", "development").strip().lower()

if ENVIRONMENT == "development":
    from .dev import *
else:
    from .prod import *
