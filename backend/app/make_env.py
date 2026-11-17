"""Create backend/.env from .env.example with freshly generated JWT_SECRET and FERNET_KEY (first run only).

Usage: python -m app.make_env   (does nothing if backend/.env already exists; never prints secret values)
"""
import secrets
import sys
from pathlib import Path

from cryptography.fernet import Fernet

BACKEND_DIR = Path(__file__).resolve().parent.parent


def make_env(target: Path = BACKEND_DIR / ".env", example: Path = BACKEND_DIR / ".env.example") -> bool:
    if target.exists():
        return False
    generated = {"JWT_SECRET": secrets.token_urlsafe(48), "FERNET_KEY": Fernet.generate_key().decode()}
    lines = []
    for line in example.read_text(encoding="utf-8").splitlines():
        key = line.split("=", 1)[0].strip()
        lines.append(f"{key}={generated[key]}" if key in generated and "=" in line else line)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


if __name__ == "__main__":
    created = make_env()
    print("[OnaRadar] backend/.env created with new JWT_SECRET and FERNET_KEY (add GEMINI_API_KEY for the AI summary)."
          if created else "[OnaRadar] backend/.env already exists.")
    sys.exit(0)
