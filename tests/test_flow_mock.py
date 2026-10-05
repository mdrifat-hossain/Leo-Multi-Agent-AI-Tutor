"""Offline smoke test: runs the full Leo flow with a fake LLM (no API key / no network)."""
import json, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ["GEMINI_API_KEY"] = "fake"
from crewai import BaseLLM

class FakeLLM(BaseLLM):
    def __init__(self):
        super().__init__(model="fake")
        self.eval_calls = 0
    def call(self, messages, tools=None, callbacks=None, available_functions=None,
             from_task=None, from_agent=None, **kw):
        text = messages if isinstance(messages, str) else " ".join(m.get("content", "") for m in messages)
        if "triaging a study request" in text:
            if "science" in text and "photosynthesis" not in text:
                return json.dumps({"status": "needs_clarification", "clarifying_question": "Which area of science?"})
            return json.dumps({"status": "ready", "topic": "Photosynthesis", "level": "beginner",
                               "learning_objectives": ["a", "b", "c"], "key_concepts": ["light", "CO2"],
                               "teaching_notes": "use analogies"})
        if "create a practice quiz" in text or "NEW follow-up quiz" in text:
            qs = [{"id": i, "concept": "light" if i % 2 else "CO2", "question": f"Question {i}?",
                   "question_type": "mcq", "options": ["A) x", "B) y", "C) z", "D) w"],
                   "correct_answer": "B) y", "explanation": "because"} for i in range(1, 6)]
            return json.dumps({"topic": "Photosynthesis", "questions": qs})
        if "Grade the student" in text:
            self.eval_calls += 1
            sc = 0.2 if self.eval_calls == 1 else 1.0
            return json.dumps({"overall_score": sc, "question_feedback": [
                {"id": i, "concept": "light", "score": sc, "is_correct": sc == 1, "feedback": "ok"} for i in (1, 2, 3)],
                "weak_concepts": [], "needs_reteach": False, "summary": "s", "encouragement": "e"})
        if "Re-teach ONLY" in text: return "## Re-teach\nSimpler analogy."
        if "closing message" in text: return "Great job!"
        if "interrupted the session" in text: return "Simple answer."
        return "## Lesson\nPlants make food from light."
    def supports_function_calling(self): return False
    def supports_stop_words(self): return False
    def get_context_window_size(self): return 8000

import leo.agents, leo.orchestrator as orch
from leo import config
orch.make_llm = lambda: FakeLLM()
from leo.memory import StudentMemory
from leo.orchestrator import LeoTutor

mem = StudentMemory(os.path.join(tempfile.mkdtemp(), "m.json"))
t = LeoTutor("Ana", "beginner", memory=mem)
r = t.start("science");                      assert r["status"] == "needs_clarification", r
r = t.start("photosynthesis");               assert r["status"] == "quiz_ready", r
assert len(r["quiz"].questions) == config.N_QUESTIONS
assert "Simple" in t.intervene("explain simpler")
r = t.submit_answers(["a", "b", "c"]);       assert r["status"] == "reteach", r        # weak -> feedback loop
r = t.submit_answers(["B", "B", "B"]);       assert r["status"] == "done", r
print(t.log.markdown()[-900:]); print("\nMEMORY:", mem.summary("Ana")); print("ALL OK")
