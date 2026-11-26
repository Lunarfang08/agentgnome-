import json
from pathlib import Path

from agentgenome.config import Settings

from apps.api.main import create_app

path = Path("docs/api/openapi.json")
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(create_app(Settings(_env_file=None)).openapi(), indent=2) + "\n")
