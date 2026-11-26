"""Initialize private local configuration without printing or replacing custom secrets."""

import os
import secrets
import tempfile
from pathlib import Path


def initialize_env(root: Path) -> bool:
    target = root / ".env"
    content = target.read_text() if target.exists() else (root / ".env.example").read_text()
    lines = content.splitlines()
    entry = next((i for i, line in enumerate(lines) if line.startswith("AG_DEV_TOKEN=")), None)
    value = lines[entry].partition("=")[2].strip().strip("\"'") if entry is not None else ""
    changed = not target.exists() or not value or value == "local-development-token-change-me"
    if changed:
        token_line = "AG_DEV_TOKEN=" + secrets.token_urlsafe(32)
        if entry is None:
            lines.append(token_line)
        else:
            lines[entry] = token_line
        fd, temporary = tempfile.mkstemp(prefix=".env.", dir=root)
        try:
            with os.fdopen(fd, "w") as output:
                output.write("\n".join(lines) + "\n")
            os.chmod(temporary, 0o600)
            os.replace(temporary, target)
        finally:
            Path(temporary).unlink(missing_ok=True)
    else:
        target.chmod(0o600)
    return changed


if __name__ == "__main__":
    updated = initialize_env(Path(__file__).resolve().parents[1])
    print(
        "Local configuration "
        + ("initialized" if updated else "already configured")
        + ". Read AG_DEV_TOKEN from .env; secrets are not printed."
    )
