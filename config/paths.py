"""Where Pond keeps its data: the database, the log and the session key.

Windows: %APPDATA%\\Pond · macOS: ~/Library/Application Support/Pond · Linux: ~/.local/share/pond
Set POND_DATA to use another folder (handy for development and tests).
"""
import os
import secrets
import sys
from pathlib import Path

APP_NAME = "Pond"


def data_dir() -> Path:
    if os.getenv("POND_DATA"):
        path = Path(os.environ["POND_DATA"])
    elif sys.platform == "win32":
        path = Path(os.getenv("APPDATA") or Path.home()) / APP_NAME
    elif sys.platform == "darwin":
        path = Path.home() / "Library" / "Application Support" / APP_NAME
    else:
        path = Path(os.getenv("XDG_DATA_HOME") or Path.home() / ".local" / "share") / APP_NAME.lower()
    path.mkdir(parents=True, exist_ok=True)
    return path


def secret_key(folder: Path) -> str:
    """Django's session signing key: created on first run, then reused."""
    path = folder / "secret.key"
    if path.exists():
        return path.read_text().strip()
    value = secrets.token_hex(32)
    path.write_text(value)
    return value
