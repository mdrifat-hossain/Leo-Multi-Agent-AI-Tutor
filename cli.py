"""Command-line interface for Leo. Works locally and inside a Kaggle notebook cell (run_cli())."""
from leo import config
from leo.events import EventLog
from leo.orchestrator import LeoTutor


def _show_quiz(quiz):
    print("\n" + "=" * 60 + "\n📝 QUIZ\n" + "=" * 60)
    for q in quiz.questions:
        print(f"\nQ{q.id} [{q.concept}] {q.question}")
        for opt in q.options:
            print(f"   {opt}")


def _show_eval(ev):
    print("\n" + "=" * 60 + f"\n✅ EVALUATION - score {ev.overall_score:.0%}\n" + "=" * 60)
    for f in ev.question_feedback:
        print(f"Q{f.id} ({f.concept}): {f.score:.0%} - {f.feedback}")
    print(f"\n{ev.summary}\n{ev.encouragement}")


def run_cli():
    print("🎓 Leo - Multi-Agent AI Tutor  (type /ask <question> to interrupt, /quit to exit)\n")
    config.get_api_key()
    name = input("Your name: ").strip() or "Student"
    level = input("Level (beginner/intermediate/advanced) [beginner]: ").strip() or "beginner"
    log = EventLog(listener=lambda e: print(e.text()))
    tutor = LeoTutor(name, level, log=log)

    res = tutor.start(input("What do you want to learn? > "))
    while res["status"] == "needs_clarification":          # Coordinator handles unclear requests
        print(f"\n🧭 Leo: {res['question']}")
        res = tutor.start(input("> "))

    while True:
        if res["status"] == "error":
            print("\n⚠️ ", res["message"])
            return
        if res["status"] in ("quiz_ready", "reteach"):
            if res["status"] == "reteach":
                _show_eval(res["evaluation"])
                print("\n🔁 Leo is re-teaching the concepts you missed...")
            print("\n" + "=" * 60 + "\n📖 LESSON\n" + "=" * 60 + f"\n{res['lesson']}")
            _show_quiz(res["quiz"])
            answers = []
            for q in res["quiz"].questions:
                while True:                                     # human-in-the-loop interruption
                    a = input(f"\nYour answer to Q{q.id} > ").strip()
                    if a.lower().startswith("/ask"):
                        print("\n💬", tutor.intervene(a[4:]))
                    elif a.lower() == "/quit":
                        return
                    else:
                        answers.append(a)
                        break
            res = tutor.submit_answers(answers)
        elif res["status"] == "needs_answers":
            print(res["message"])
            res = tutor.submit_answers([input("Answer > ")])
        elif res["status"] == "done":
            _show_eval(res["evaluation"])
            print("\n🎉 " + res["wrapup"])
            print(f"\n📈 Progress: {res['history']}")
            return


if __name__ == "__main__":
    run_cli()
