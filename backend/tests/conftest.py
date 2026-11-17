import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

# Tests use their own SQLite file and never need real secrets.
os.environ["DATABASE_URL"] = "sqlite:///./test_onaradar.db"
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ.setdefault("FERNET_KEY", "x" * 43 + "=")  # replaced below with a valid key

from cryptography.fernet import Fernet  # noqa: E402

os.environ["FERNET_KEY"] = Fernet.generate_key().decode()
os.environ["JWT_SECRET"] = "test-secret"
