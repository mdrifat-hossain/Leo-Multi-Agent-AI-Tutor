"""Persistent student memory (JSON). Remembers WHO the student is and WHAT they studied,
how they scored and which concepts were weak. It is injected into every prompt."""
import json
import threading
import time
from pathlib import Path
from typing import List


class StudentMemory:
    def __init__(self, path):
        self.path = Path(path)
        self._lock = threading.Lock()
        self.data = self._load()

    def _load(self) -> dict:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {"students": {}}

    def _save(self) -> None:
        try:
            self.path.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
        except Exception:
            pass  # memory must never crash a session

    def _profile(self, name: str) -> dict:
        return self.data.setdefault("students", {}).setdefault(
            name.lower(), {"name": name, "sessions": 0, "topics": {}}
        )

    def start_session(self, name: str, topic: str, level: str) -> None:
        with self._lock:
            p = self._profile(name)
            p["sessions"] += 1
            p["level"] = level
            t = p["topics"].setdefault(topic, {"attempts": 0, "best_score": 0.0, "weak_concepts": []})
            t["last_studied"] = time.strftime("%Y-%m-%d %H:%M")
            self._save()

    def record_round(self, name: str, topic: str, score: float, weak: List[str]) -> None:
        with self._lock:
            t = self._profile(name)["topics"].setdefault(
                topic, {"attempts": 0, "best_score": 0.0, "weak_concepts": []})
            t["attempts"] += 1
            t["last_score"] = round(score, 2)
            t["best_score"] = max(t.get("best_score", 0.0), round(score, 2))
            t["weak_concepts"] = weak
            self._save()

    def summary(self, name: str) -> str:
        p = self.data.get("students", {}).get(name.lower())
        if not p or not p.get("topics"):
            return "New student - no previous history."
        parts = []
        for topic, t in list(p["topics"].items())[-4:]:
            weak = ", ".join(t.get("weak_concepts", [])) or "none"
            parts.append(f"{topic} (best {t.get('best_score', 0):.0%}, weak concepts: {weak})")
        return (f"Returning student ({p['sessions']} earlier sessions, usual level "
                f"{p.get('level', 'beginner')}). Past topics: " + "; ".join(parts))
