from pathlib import Path


def _load_version(default: str = "0.1.0") -> str:
    try:
        version_path = Path(__file__).resolve().parent.parent.parent / "VERSION"
        with open(version_path, "r", encoding="ascii") as f:
            line = f.readline().strip()
            return line or default
    except Exception:
        return default


__version__ = _load_version()

__all__ = ["__version__"]
