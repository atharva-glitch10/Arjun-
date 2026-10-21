"""Runtime config. Temperatures are FIXED constants - never changed at runtime."""

import os

EXTRACTION_TEMPERATURE = 0.0  # care mode / intent extraction / distress: always 0
# UNVERIFIED: Gnani's model-card recommendation. Must be chosen by our own testing before launch.
COMPANION_TEMPERATURE = 0.6
COMPANION_TOP_P = 0.95

EVON_BASE_URL = os.environ.get("EVON_BASE_URL", "")
EVON_MODEL = os.environ.get("EVON_MODEL", "gnani/gnani-evon-v3.3-30B-A3B")
# Only for a hosted non-vLLM LLM used in development (CLAUDE.md open question 5): its bearer key,
# and "0" to drop the vLLM-only chat_template_kwargs field some providers reject.
EVON_API_KEY = os.environ.get("EVON_API_KEY", "")
EVON_SEND_TEMPLATE_KWARGS = os.environ.get("EVON_SEND_TEMPLATE_KWARGS", "1") == "1"
CORE_API_URL = os.environ.get("CORE_API_URL", "http://core-api:8000")
CORE_API_KEY = os.environ.get("CORE_API_KEY", "")
SCHEMA_DIR = os.environ.get(
    "SHARED_SCHEMA_DIR",
    os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "shared", "schemas")),
)

ELDERLINE_NUMBER = "14567"  # govt senior helpline, 8 AM - 8 PM
LONG_STORY_WORDS = 15  # a CHAT turn at least this long triggers a "keep this story?" consent ask
