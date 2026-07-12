import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

QUOTA_STATE_FILE = Path("data/youtube_quota_state.json")


class YouTubeProjectManager:
    def __init__(self, config: dict):
        self.projects = [p for p in config.get("projects", []) if p.get("active", False)]
        self.rotation_cfg = config.get("rotation", {})
        self.strategy = self.rotation_cfg.get("strategy", "least_used")
        self.default_cost = self.rotation_cfg.get("cost_per_upload", 1600)
        self.safety_margin = self.rotation_cfg.get("quota_safety_margin", 1000)

        self._exhausted_in_session: set[str] = set()
        self._quota_state = self._load_quota_state()
        self._reset_if_new_day()

    def _load_quota_state(self) -> dict:
        if QUOTA_STATE_FILE.exists():
            try:
                with open(QUOTA_STATE_FILE, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        return {"date": "", "usage": {}}

    def _save_quota_state(self):
        QUOTA_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(QUOTA_STATE_FILE, "w") as f:
            json.dump(self._quota_state, f, indent=2)

    def _reset_if_new_day(self):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self._quota_state.get("date") != today:
            self._quota_state = {"date": today, "usage": {}}
            self._save_quota_state()

    def get_available_project(self, exclude: Optional[list[str]] = None) -> Optional[dict]:
        exclude = set(exclude or []) | self._exhausted_in_session
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        usage = self._quota_state.get("usage", {})

        candidates = []
        for p in self.projects:
            name = p["name"]
            if name in exclude:
                continue
            limit = p.get("daily_quota_limit", 10000)
            used = usage.get(name, 0)
            remaining = limit - used
            if remaining >= self.default_cost + self.safety_margin:
                candidates.append((name, remaining, p))

        if not candidates:
            return None

        if self.strategy == "least_used":
            candidates.sort(key=lambda x: -x[1])

        return candidates[0][2]

    def record_usage(self, project_name: str, cost: Optional[int] = None):
        cost = cost or self.default_cost
        usage = self._quota_state.setdefault("usage", {})
        usage[project_name] = usage.get(project_name, 0) + cost
        self._save_quota_state()

    def mark_exhausted(self, project_name: str):
        self._exhausted_in_session.add(project_name)

    @property
    def usage_summary(self) -> dict:
        return dict(self._quota_state.get("usage", {}))
