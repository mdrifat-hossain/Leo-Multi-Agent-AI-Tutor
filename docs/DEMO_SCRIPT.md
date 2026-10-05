# Demo video script (target 4 min, limit 3-5 min)

| Time | What to show | What to say |
|------|--------------|-------------|
| 0:00-0:30 | README architecture diagram, then the running app | "This is Leo, a multi-agent tutor built with CrewAI. Four agents: Coordinator, Explainer, Quiz Master, Evaluator. Orchestration is sequential and controlled by the Coordinator." |
| 0:30-1:00 | Type a **vague** request ("science") and press Start | "The Coordinator detects an unclear request and asks one clarifying question instead of guessing." |
| 1:00-1:40 | Reply "photosynthesis". Point at the **Live agent activity** panel | "Coordinator plans -> hands the plan to the Explainer -> the lesson is handed to the Quiz Master, who returns structured JSON." |
| 1:40-2:10 | Open **Interrupt Leo** and ask "explain it simpler" | "Human-in-the-loop: I interrupt mid-run, the Coordinator routes the question to the Explainer." |
| 2:10-3:00 | Answer the quiz **badly on purpose**, submit | "The Quiz Master's questions plus my answers are handed to the Evaluator, who grades with partial credit and detects weak concepts." |
| 3:00-3:40 | Show feedback-loop re-teach + new quiz, answer correctly | "Score was under 70%, so the weak concepts go back to the Explainer: this is the feedback loop (bonus). The Quiz Master makes a new quiz." |
| 3:40-4:10 | Show wrap-up, progress, then re-open a new session with same name | "The Coordinator wraps up. Memory remembers my topic, score and weak concepts for next time." |

Tips: record at 1080p, keep the activity panel visible, run once beforehand so the model is warm.
