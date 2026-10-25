"""Snapshot contracts for the external integration team, no server required."""
import importlib
import json
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
target = root / 'docs' / 'openapi'
target.mkdir(exist_ok=True)
for service in ('personnel', 'inventory', 'commerce'):
    app = importlib.import_module(f'services.{service}.app').app
    (target / f'{service}.json').write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Exported {service}')
