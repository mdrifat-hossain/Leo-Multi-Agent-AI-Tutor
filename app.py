"""Gradio interface for Leo. Shows a LIVE activity panel: which agent is doing what, and the handoffs.

Run locally:   python app.py
Run on Kaggle: see notebooks/leo_kaggle.ipynb  (launches with share=True)
"""
import os
import threading
import time

import gradio as gr

from leo import config
from leo.orchestrator import LeoTutor

MAXQ = 5
NOUT = 13  # state, activity, status, lesson, quiz, answers_col, 5 answer boxes, eval, side


# ------------------------------------------------------------------ rendering helpers
def md_quiz(quiz) -> str:
    out = ["### 📝 Quiz Master's questions"]
    for q in quiz.questions:
        out.append(f"**Q{q.id}.** *(concept: {q.concept})* {q.question}")
        out += [f"&nbsp;&nbsp;&nbsp;{o}  " for o in q.options]
        out.append("")
    return "\n".join(out)


def md_eval(ev) -> str:
    out = [f"### ✅ Evaluator's report - score **{ev.overall_score:.0%}**"]
    for f in ev.question_feedback:
        mark = "✔️" if f.score >= 0.7 else "❌"
        out.append(f"- {mark} **Q{f.id}** ({f.concept}) - {f.score:.0%}: {f.feedback}")
    if ev.weak_concepts:
        out.append(f"\n**Weak concepts:** {', '.join(ev.weak_concepts)}")
    out.append(f"\n{ev.summary}  \n*{ev.encouragement}*")
    return "\n".join(out)


def keep(n=1):
    return tuple(gr.update() for _ in range(n))


def live_ui(tutor, activity):
    return (tutor, activity) + keep(NOUT - 2)


def final_ui(tutor, res):
    activity = tutor.log.markdown() if tutor else ""
    st = res["status"]

    if st == "side":  # human-in-the-loop answer: only touch the side panel
        return (tutor, activity) + keep(NOUT - 3) + (f"### 💬 Explainer's reply\n{res['text']}",)

    status, lesson, quiz, ev_md = gr.update(), gr.update(), gr.update(), gr.update()
    show, nq = False, 0
    answers_untouched = False

    if st == "needs_clarification":
        status = (f"### 🧭 Leo needs a bit more information\n{res['question']}\n\n"
                  "*Type your answer in the box above and press **Start / Reply** again.*")
    elif st == "needs_answers":
        status = f"### ⚠️ {res['message']}"
        answers_untouched = True
    elif st in ("quiz_ready", "reteach"):
        nq = len(tutor.quiz.questions)
        show = True
        rnd = res.get("round", 1)
        status = (f"### 🙋 Your turn - round {rnd}/{config.MAX_ROUNDS}\n"
                  "Answer the questions below. You can also **interrupt Leo** with a question.")
        head = "## 🔁 Re-teaching (feedback loop)\n" if st == "reteach" else "## 📖 Lesson\n"
        lesson, quiz = head + res["lesson"], md_quiz(tutor.quiz)
        if st == "reteach":
            ev_md = md_eval(res["evaluation"])
    elif st == "done":
        status = "### 🎉 Session complete"
        ev_md = md_eval(res["evaluation"]) + f"\n\n---\n#### 🧭 Coordinator's wrap-up\n{res['wrapup']}" \
                f"\n\n📈 **Progress:** {res['history']}"
        quiz = ""
    else:  # error
        status = f"### ⚠️ {res.get('message', 'Something went wrong.')}"
        answers_untouched = True

    if answers_untouched:
        col, ans = gr.update(), [gr.update() for _ in range(MAXQ)]
    else:
        col = gr.update(visible=show)
        ans = [gr.update(visible=show and i < nq, value="", label=f"Your answer to Q{i + 1}")
               for i in range(MAXQ)]
    return (tutor, activity, status, lesson, quiz, col, *ans, ev_md, gr.update())


def run_live(tutor, fn, wrap=lambda r: r):
    """Run an orchestrator call in a thread and stream the agent activity log to the UI."""
    box = {}

    def work():
        try:
            box["r"] = wrap(fn())
        except Exception as exc:  # last-resort guard so the UI never crashes
            box["r"] = {"status": "error", "message": f"Unexpected problem: {exc}"}

    t = threading.Thread(target=work, daemon=True)
    t.start()
    while t.is_alive():
        yield live_ui(tutor, tutor.log.markdown())
        time.sleep(0.8)
    t.join()
    yield final_ui(tutor, box["r"])


# ------------------------------------------------------------------ event handlers
def on_start(name, topic, level, tutor):
    if tutor is None or not tutor.awaiting_clarification:
        try:
            tutor = LeoTutor(name or "Student", level)
        except Exception as exc:
            yield final_ui(None, {"status": "error", "message": str(exc)})
            return
    yield from run_live(tutor, lambda: tutor.start(topic))


def on_submit(tutor, *answers):
    if tutor is None or not tutor.quiz:
        yield final_ui(tutor, {"status": "error", "message": "Start a session first."})
        return
    yield from run_live(tutor, lambda: tutor.submit_answers(list(answers)))


def on_ask(tutor, message):
    if tutor is None:
        yield final_ui(None, {"status": "side", "text": "Start a session first, then interrupt me anytime."})
        return
    yield from run_live(tutor, lambda: tutor.intervene(message),
                        wrap=lambda txt: {"status": "side", "text": txt})


# ------------------------------------------------------------------ layout
with gr.Blocks(title="Leo - Multi-Agent AI Tutor") as demo:
    gr.Markdown("# 🎓 Leo - Multi-Agent AI Tutor\n"
                "🧭 Coordinator → 📖 Explainer → 📝 Quiz Master → ✅ Evaluator "
                "(+ feedback loop and human-in-the-loop)")
    tutor_state = gr.State(None)

    with gr.Row():
        with gr.Column(scale=2):
            name = gr.Textbox(label="Your name", value="Student")
            topic = gr.Textbox(label="What do you want to learn?",
                               placeholder="e.g. photosynthesis, Python loops, Pythagorean theorem")
            level = gr.Dropdown(["beginner", "intermediate", "advanced"], value="beginner", label="Level")
            start_btn = gr.Button("🚀 Start / Reply to Leo", variant="primary")
            status_md = gr.Markdown()
            lesson_md = gr.Markdown()
            quiz_md = gr.Markdown()
            with gr.Column(visible=False) as answers_col:
                a_boxes = [gr.Textbox(visible=False, lines=2) for _ in range(MAXQ)]
                submit_btn = gr.Button("✅ Submit answers to the Evaluator", variant="primary")
            with gr.Accordion("✋ Interrupt Leo (human-in-the-loop)", open=False):
                ask_box = gr.Textbox(label="Ask a question or request a simpler explanation")
                ask_btn = gr.Button("Send to Explainer")
                side_md = gr.Markdown()
            eval_md = gr.Markdown()
        with gr.Column(scale=1):
            gr.Markdown("### 🧑‍🤝‍🧑 Live agent activity")
            activity_md = gr.Markdown("_No activity yet._")

    outs = [tutor_state, activity_md, status_md, lesson_md, quiz_md, answers_col, *a_boxes, eval_md, side_md]
    start_btn.click(on_start, [name, topic, level, tutor_state], outs)
    topic.submit(on_start, [name, topic, level, tutor_state], outs)
    submit_btn.click(on_submit, [tutor_state, *a_boxes], outs)
    ask_btn.click(on_ask, [tutor_state, ask_box], outs)


if __name__ == "__main__":
    on_kaggle = os.path.exists("/kaggle")
    demo.queue().launch(share=on_kaggle or os.getenv("LEO_SHARE") == "1")
