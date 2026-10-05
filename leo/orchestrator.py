"""Leo's orchestration layer.

Pattern: SEQUENTIAL pipelines (CrewAI Process.sequential) controlled by the COORDINATOR agent.

  Phase 1  Coordinator  --plan-->  (clarify? -> student)           [triage crew]
  Phase 2  Explainer --lesson--> Quiz Master --quiz JSON-->        [teach crew, task context handoff]
           ... student answers (human in the loop) ...
  Phase 3  Evaluator --evaluation JSON--> Coordinator              [evaluate crew]
  Phase 4  weak?  Evaluator --feedback--> Explainer (re-teach) --> Quiz Master (new quiz) -> loop
           else   Coordinator --wrap-up--> student                 [feedback loop = bonus]
"""
from __future__ import annotations

import json
import re
import time
from typing import Callable, List, Optional

from crewai import Crew, Process, Task

from . import config, prompts
from .agents import build_agents, make_llm
from .events import LABEL, EventLog
from .memory import StudentMemory
from .schemas import Evaluation, Plan, Quiz

MAX_CLARIFICATIONS = 2


class AgentFailure(Exception):
    """Raised when an agent keeps failing after all Coordinator retries."""


def _clip(err, n: int = 140) -> str:
    return str(err).replace("\n", " ")[:n]


def _parse(task_output, model):
    """Get a validated pydantic object from a TaskOutput (native output, or JSON in raw text)."""
    obj = getattr(task_output, "pydantic", None)
    if isinstance(obj, model):
        return obj
    raw = (getattr(task_output, "raw", "") or "").replace("```json", "").replace("```", "")
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("agent did not return JSON")
    return model.model_validate(json.loads(raw[start:end + 1], strict=False))


def _text(task_output) -> str:
    txt = (getattr(task_output, "raw", "") or "").strip()
    if not txt:
        raise ValueError("agent returned empty text")
    return txt


class LeoTutor:
    def __init__(self, student_name: str = "Student", level: str = "beginner",
                 log: Optional[EventLog] = None, memory: Optional[StudentMemory] = None):
        self.name = (student_name or "Student").strip() or "Student"
        self.level = level or "beginner"
        self.log = log or EventLog()
        self.memory = memory or StudentMemory(config.MEMORY_PATH)
        self.agents = build_agents(make_llm())

        # session state (short-term memory)
        self.request_history: List[str] = []
        self.awaiting_clarification = False
        self.clarifications = 0
        self.plan: Optional[Plan] = None
        self.lesson = ""
        self.quiz: Optional[Quiz] = None
        self.round = 0
        self.evaluations: List[Evaluation] = []

    # ------------------------------------------------------------------ helpers
    def _task(self, agent_key, description, expected, *, context=None, model=None,
              next_agent=None, done_msg="") -> Task:
        def callback(_output):
            self.log.emit(agent_key, "done", done_msg or "finished")
            if next_agent:
                self.log.emit(next_agent, "handoff",
                              f"received the work of {LABEL[agent_key]} - now working...")
        kw = dict(description=description, expected_output=expected,
                  agent=self.agents[agent_key], callback=callback)
        if context:
            kw["context"] = context
        if model:
            kw["output_pydantic"] = model
        return Task(**kw)

    def _crew(self, keys, tasks) -> Crew:
        return Crew(agents=[self.agents[k] for k in keys], tasks=tasks,
                    process=Process.sequential, verbose=config.VERBOSE)

    def _run(self, label: str, build: Callable[[], Crew], parse: Callable):
        """Coordinator's safety net: retry stalled / failing / malformed agent runs."""
        last = None
        for attempt in range(1, config.MAX_RETRIES + 1):
            try:
                return parse(build().kickoff())
            except Exception as exc:  # timeout, API error, bad JSON ...
                last = exc
                if attempt < config.MAX_RETRIES:
                    self.log.emit("coordinator", "warning",
                                  f"{label} hit a problem ({_clip(exc)}). Retry {attempt}/"
                                  f"{config.MAX_RETRIES - 1}...")
                    time.sleep(2 * attempt)
        self.log.emit("coordinator", "warning", f"{label} failed after {config.MAX_RETRIES} attempts.")
        raise AgentFailure(f"{label} failed: {_clip(last)}")

    def _error(self, exc: Exception) -> dict:
        return {"status": "error",
                "message": ("Sorry - one of Leo's agents could not finish ("
                            f"{_clip(exc, 200)}). Your progress is safe, please press the button again.")}

    @staticmethod
    def _number(quiz: Quiz) -> Quiz:
        if not quiz.questions:
            raise ValueError("quiz has no questions")
        quiz.questions = quiz.questions[:config.N_QUESTIONS]
        for i, q in enumerate(quiz.questions, 1):
            q.id = i
        return quiz

    # ------------------------------------------------------------------ phase 1+2
    def start(self, request: str) -> dict:
        request = (request or "").strip()
        self.request_history.append(request)
        full_request = " | ".join(r for r in self.request_history if r)

        if not full_request:  # Coordinator handles empty input without even calling the LLM
            self.log.emit("coordinator", "warning", "Empty request -> asking the student for a topic.")
            self.awaiting_clarification = True
            return {"status": "needs_clarification",
                    "question": "What would you like to learn today? For example: photosynthesis, "
                                "Python loops, or the Pythagorean theorem."}

        self.log.emit("coordinator", "start", "Reading your request and planning the session...")
        mem = self.memory.summary(self.name)
        try:
            plan: Plan = self._run(
                "Planning",
                lambda: self._crew(["coordinator"], [self._task(
                    "coordinator",
                    prompts.PLAN_TASK.substitute(student=self.name, level=self.level,
                                                 memory=mem, request=full_request),
                    prompts.PLAN_EXPECTED, model=Plan, next_agent=None,
                    done_msg="Request analysed")]),
                lambda r: _parse(r.tasks_output[0], Plan))
        except AgentFailure as exc:
            return self._error(exc)

        if plan.status == "needs_clarification" and self.clarifications < MAX_CLARIFICATIONS:
            self.clarifications += 1
            self.awaiting_clarification = True
            q = plan.clarifying_question or "Could you tell me a more specific topic you'd like to learn?"
            self.log.emit("coordinator", "handoff", f"Request unclear -> asking the student: {q}")
            return {"status": "needs_clarification", "question": q}

        # Ready (or clarification budget exhausted: Coordinator picks a sensible default)
        if plan.status != "ready" or not plan.topic:
            plan.topic = plan.topic or full_request[:80] or "Study skills basics"
            plan.status = "ready"
            self.log.emit("coordinator", "info", f"Still vague - choosing a focused topic: {plan.topic}")
        self.awaiting_clarification = False
        self.plan = plan
        self.round = 1
        self.memory.start_session(self.name, plan.topic, plan.level)
        self.log.emit("coordinator", "done", f"Plan ready for '{plan.topic}' -> delegating to Explainer")
        return self._teach_and_quiz(mem)

    def _teach_and_quiz(self, mem: str) -> dict:
        plan_json = self.plan.model_dump_json(indent=2)
        self.log.emit("explainer", "start", "Writing a lesson tailored to you...")

        def build():
            lesson = self._task("explainer",
                                prompts.LESSON_TASK.substitute(student=self.name, plan=plan_json, memory=mem),
                                prompts.LESSON_EXPECTED, next_agent="quiz_master",
                                done_msg="Lesson written -> handing it to the Quiz Master")
            quiz = self._task("quiz_master",
                              prompts.QUIZ_TASK.substitute(n=config.N_QUESTIONS, plan=plan_json),
                              prompts.QUIZ_EXPECTED, context=[lesson], model=Quiz,
                              done_msg="Quiz created (structured JSON) -> ready for the student")
            return self._crew(["explainer", "quiz_master"], [lesson, quiz])

        try:
            self.lesson, self.quiz = self._run(
                "Teaching + quiz", build,
                lambda r: (_text(r.tasks_output[0]), self._number(_parse(r.tasks_output[1], Quiz))))
        except AgentFailure as exc:
            return self._error(exc)
        return {"status": "quiz_ready", "lesson": self.lesson, "quiz": self.quiz, "round": self.round}

    # ------------------------------------------------------------------ human in the loop
    def intervene(self, message: str) -> str:
        """Student interrupts mid-run -> Coordinator routes the message to the Explainer."""
        message = (message or "").strip()
        if not message or not self.plan:
            return "Start a session first, then you can interrupt Leo with a question."
        self.log.emit("student", "human", f"Interrupted: \"{message[:80]}\"")
        self.log.emit("coordinator", "handoff", "Routing the student's question to the Explainer")
        self.log.emit("explainer", "start", "Answering the student's question...")
        try:
            return self._run(
                "Student question",
                lambda: self._crew(["explainer"], [self._task(
                    "explainer",
                    prompts.ASK_TASK.substitute(topic=self.plan.topic, lesson=self.lesson[:2500],
                                                message=message.replace('"', "'")),
                    prompts.ASK_EXPECTED, done_msg="Answered the student's question")]),
                lambda r: _text(r.tasks_output[0]))
        except AgentFailure:
            return "I couldn't answer that right now - please try rephrasing your question."

    # ------------------------------------------------------------------ phase 3+4
    def submit_answers(self, answers: List[str]) -> dict:
        if not self.quiz:
            return {"status": "error", "message": "No active quiz. Start a session first."}
        qs = self.quiz.questions
        answers = [(a or "").strip() for a in (answers + [""] * len(qs))[:len(qs)]]
        if not any(answers):
            self.log.emit("coordinator", "warning", "No answers received - asking the student to try.")
            return {"status": "needs_answers",
                    "message": "Please write at least one answer (even a guess is fine) before submitting."}

        answers_text = "\n".join(f"Q{q.id}: {a or '(no answer)'}" for q, a in zip(qs, answers))
        self.log.emit("student", "info", "Submitted answers")
        self.log.emit("evaluator", "handoff", "Received the Quiz Master's questions + the student's answers")
        quiz_json = self.quiz.model_dump_json(indent=2)

        try:
            ev: Evaluation = self._run(
                "Evaluation",
                lambda: self._crew(["evaluator"], [self._task(
                    "evaluator",
                    prompts.EVAL_TASK.substitute(student=self.name, topic=self.plan.topic, quiz=quiz_json,
                                                 answers=answers_text, pass_score=config.PASS_SCORE),
                    prompts.EVAL_EXPECTED, model=Evaluation,
                    done_msg="Answers graded -> sending the report to the Coordinator")]),
                lambda r: _parse(r.tasks_output[0], Evaluation))
        except AgentFailure as exc:
            return self._error(exc)

        # Deterministic post-processing (don't blindly trust the LLM's arithmetic)
        for f in ev.question_feedback:
            f.score = max(0.0, min(1.0, f.score))
        if ev.question_feedback:
            ev.overall_score = round(sum(f.score for f in ev.question_feedback) / len(ev.question_feedback), 2)
        ev.overall_score = max(0.0, min(1.0, ev.overall_score))
        weak = set(ev.weak_concepts) | {f.concept for f in ev.question_feedback if f.concept and f.score < 0.7}
        ev.weak_concepts = sorted(weak)
        ev.needs_reteach = ev.overall_score < config.PASS_SCORE
        self.evaluations.append(ev)
        self.memory.record_round(self.name, self.plan.topic, ev.overall_score, ev.weak_concepts)
        self.log.emit("coordinator", "info",
                      f"Round {self.round}: score {ev.overall_score:.0%}, weak concepts: "
                      f"{', '.join(ev.weak_concepts) or 'none'}")

        # ---- BONUS feedback loop: weak answers go back to the Explainer ----
        if ev.needs_reteach and self.round < config.MAX_ROUNDS:
            self.log.emit("coordinator", "handoff",
                          "Score below threshold -> sending weak concepts back to the Explainer (feedback loop)")
            res = self._reteach(ev)
            if res:
                return res
        return self._wrap_up(ev)

    def _reteach(self, ev: Evaluation) -> Optional[dict]:
        weak = ", ".join(ev.weak_concepts) or self.plan.topic
        feedback = json.dumps([f.model_dump() for f in ev.question_feedback if f.score < 0.7], indent=2)
        old = "; ".join(q.question for q in self.quiz.questions)
        self.log.emit("explainer", "start", f"Re-teaching: {weak}")

        def build():
            re_t = self._task("explainer",
                              prompts.RETEACH_TASK.substitute(student=self.name, weak=weak, feedback=feedback,
                                                              previous=self.lesson[:1500]),
                              prompts.RETEACH_EXPECTED, next_agent="quiz_master",
                              done_msg="Re-teaching done -> handing over to the Quiz Master")
            q_t = self._task("quiz_master",
                             prompts.RETEACH_QUIZ_TASK.substitute(weak=weak, old=old, n=config.N_QUESTIONS,
                                                                  topic=self.plan.topic),
                             prompts.QUIZ_EXPECTED, context=[re_t], model=Quiz,
                             done_msg="New follow-up quiz ready")
            return self._crew(["explainer", "quiz_master"], [re_t, q_t])

        try:
            self.lesson, self.quiz = self._run(
                "Re-teach + new quiz", build,
                lambda r: (_text(r.tasks_output[0]), self._number(_parse(r.tasks_output[1], Quiz))))
        except AgentFailure:
            self.log.emit("coordinator", "warning", "Re-teaching failed - wrapping up the session instead.")
            return None
        self.round += 1
        return {"status": "reteach", "evaluation": ev, "lesson": self.lesson,
                "quiz": self.quiz, "round": self.round}

    def _wrap_up(self, ev: Evaluation) -> dict:
        history = "; ".join(f"round {i}: {e.overall_score:.0%}" for i, e in enumerate(self.evaluations, 1))
        self.log.emit("coordinator", "start", "Writing the session wrap-up...")
        try:
            msg = self._run(
                "Wrap-up",
                lambda: self._crew(["coordinator"], [self._task(
                    "coordinator",
                    prompts.WRAPUP_TASK.substitute(student=self.name, topic=self.plan.topic, history=history,
                                                   weak=", ".join(ev.weak_concepts) or "none",
                                                   memory=self.memory.summary(self.name)),
                    prompts.WRAPUP_EXPECTED, done_msg="Session complete")]),
                lambda r: _text(r.tasks_output[0]))
        except AgentFailure:
            msg = ev.summary or "Great work today! Come back anytime to keep practising."
        self.quiz = None
        return {"status": "done", "evaluation": ev, "wrapup": msg, "history": history}
