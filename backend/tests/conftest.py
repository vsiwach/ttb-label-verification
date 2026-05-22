"""Test environment setup.

Force INFERENCE_MODE=mock so tests never depend on the local .env file or any
cloud API key. Runs before app imports because conftest.py is loaded first.
"""

import os

os.environ["INFERENCE_MODE"] = "mock"
os.environ.setdefault("ANTHROPIC_API_KEY", "")
os.environ.setdefault("OPENAI_API_KEY", "")
os.environ.setdefault("GOOGLE_API_KEY", "")
