"""Tiny event log so the UI/CLI can show WHICH agent is doing WHAT."""
import threading
import time
from dataclasses import dataclass
from typing import Callable, List, Optional

META = {
    "coordinator": ("🧭", "Coordinator"),
    "explainer": ("📖", "Explainer"),
    "quiz_master": ("📝", "Quiz Master"),
    "evaluator": ("✅", "Evaluator"),
    "student": ("🙋", "Student"),
}
LABEL = {k: v[1] for k, v in META.items()}
KIND_ICON = {"start": "▶️", "done": "✔️", "handoff": "➡️", "warning": "⚠️",
             "info": "ℹ️", "human": "✋"}


@dataclass
class Event:
    ts: str
    agent: str
    kind: str
    message: str

    def text(self) -> str:
        icon, name = META.get(self.agent, ("🤖", self.agent))
        return f"[{self.ts}] {icon} {name:<11} {KIND_ICON.get(self.kind, '')} {self.message}"

    def markdown(self) -> str:
        icon, name = META.get(self.agent, ("🤖", self.agent))
        return f"`{self.ts}` {icon} **{name}** {KIND_ICON.get(self.kind, '')} {self.message}"


class EventLog:
    def __init__(self, listener: Optional[Callable[[Event], None]] = None):
        self.events: List[Event] = []
        self.listener = listener
        self._lock = threading.Lock()

    def emit(self, agent: str, kind: str, message: str) -> None:
        ev = Event(time.strftime("%H:%M:%S"), agent, kind, message)
        with self._lock:
            self.events.append(ev)
        if self.listener:
            self.listener(ev)

    def markdown(self, last: int = 40) -> str:
        with self._lock:
            evs = self.events[-last:]
        return "\n\n".join(e.markdown() for e in evs) or "_No activity yet._"
