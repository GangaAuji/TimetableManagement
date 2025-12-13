import sys
from pathlib import Path
# Ensure project root is on sys.path when running from scripts/
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from app import create_app
app = create_app()
with app.app_context():
    rules = sorted([(r.endpoint, r.rule, sorted(r.methods)) for r in app.url_map.iter_rules()])
    for endpoint, rule, methods in rules:
        print(f"{endpoint} -> {rule}  methods={methods}")
