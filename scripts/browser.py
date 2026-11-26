"""Run browser checks using the private development token from local configuration."""

import os
import subprocess

from agentgenome.config import Settings

if __name__ == "__main__":
    settings = Settings()
    if settings.profile != "dev" or not settings.dev_auth:
        raise SystemExit("Browser demo tests require explicit development identity")
    env = {**os.environ, "AG_DEV_TOKEN": settings.dev_token.get_secret_value()}
    raise SystemExit(
        subprocess.call(["npm", "run", "test:e2e", "--workspace", "apps/dashboard"], env=env)
    )
