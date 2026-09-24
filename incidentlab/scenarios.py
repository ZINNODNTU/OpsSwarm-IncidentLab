import yaml
from pathlib import Path

PATH = Path("experiments/scenarios.yaml")

def scenarios():
    data = yaml.safe_load(PATH.read_text(encoding="utf-8")) or {}
    return data.get("scenarios", [])

def get(scenario_id):
    return next((x for x in scenarios() if x["id"] == scenario_id), None)
