import json
from pathlib import Path

CHANGELOG_PATH = Path(__file__).resolve().parent / 'changelog.json'


def changelog_context(request):
    with open(CHANGELOG_PATH, encoding='utf-8') as f:
        changelog = json.load(f)
    current_version = changelog[0]['version'] if changelog else None
    return {'changelog': changelog, 'current_version': current_version}
