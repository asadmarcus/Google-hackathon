# Antigravity Playbook — operating, artifacts, credits

> How to actually drive Antigravity so it rebuilds CIRO, produces the artifacts the hackathon
> grades, and doesn't burn your credits. Antigravity's UI evolves — verify exact menu names in
> your installed version; the concepts below are stable.

---

## 1. What Antigravity is

Google Antigravity is an **agent-first development platform** (an IDE built on a VS Code fork).
You don't mostly type code — you **brief agents**, they **plan**, **implement**, **test in a
browser**, and hand back **Artifacts**. It has two main surfaces:

- **Editor** — a familiar VS Code-style editor with an inline agent.
- **Agent Manager** — a mission-control view where you spawn and supervise agents across the
  Editor, Terminal and Browser. This is where you paste the prompts from `04_BUILD_PROMPTS.md`.

Models available (free tier): **Gemini 3 Flash** (cheapest), **Gemini 3 Pro**,
**Claude Sonnet 4.6**, **Claude Opus 4.6**, GPT-OSS 120B.

---

## 2. Artifacts — what the hackathon actually wants

Antigravity agents produce **Artifacts** — durable, reviewable deliverables. These ARE the
"Antigravity trace/logs" deliverable. The mapping:

| Hackathon deliverable bullet | Antigravity artifact |
|------------------------------|----------------------|
| Workplan | The **Implementation Plan** artifact |
| Task plan | The **Task List** artifact |
| Reasoning steps / decisions | The agent's reasoning shown in the Implementation Plan + the run trace in the Agent Manager |
| Tool calls / action execution | The agent's terminal/tool log in the Agent Manager run |
| Error recovery | Any retry/fix steps the agent logs during a run |
| Final outcomes / verification | The **Walkthrough** artifact (incl. screenshots / browser recording) |

How they're produced:
- The **Implementation Plan** and **Task List** are generated *before* the agent writes code —
  that's why Prompt A1 / B0 explicitly ask for them.
- **Walkthroughs** (with screenshots and, where the agent uses the browser, recordings) are
  generated after the agent verifies the work — that's why Prompts A3/A4 ask the agent to run
  the app and open the dashboards in the browser.
- You **review and steer** artifacts by leaving **Google-Docs-style comments** on them. That is
  cheaper than a new prompt and keeps the current run going.

> Make every prompt end with "produce an Implementation Plan / Task List / Walkthrough artifact"
> so the evidence exists explicitly. Don't assume — ask for it.

---

## 3. Credit efficiency — the rules that matter

The free tier is roughly **~20 agent requests/day, weekly refresh**. One "request" ≈ one agent
turn. Treat it like a tight budget.

1. **Default to Gemini 3 Flash.** It has the lowest credit consumption and a faster refresh.
   Use Gemini 3 Pro or Claude only for the one or two hardest turns (e.g. Prompt B4 — Agent 3).
2. **One phase per turn.** The prompts in `04_BUILD_PROMPTS.md` are sized so each is a complete
   unit of work. Don't split them into chatty back-and-forth.
3. **Strategy A, not B.** A is ~5 turns; B is ~9. A leaves headroom for re-runs; B doesn't.
4. **Review before approving.** Set the artifact-review policy so the agent pauses on the
   Implementation Plan. Catch mistakes in the plan (free to fix via comment) instead of after
   the agent has written code (expensive to redo).
5. **Comment, don't restart.** Steering via artifact comments continues the current run; a fresh
   prompt is a fresh turn.
6. **Don't make it retype known-good code.** Strategy A verifies your existing code — that's a
   read, not a regeneration. Reads are cheap; regeneration is not.
7. **Batch verification.** Prompt A3 runs the *entire* checklist in one turn rather than one
   endpoint per turn.
8. **Do the easy stuff yourself in the Editor.** Creating `.env`, deleting the stray files,
   `pip install` — you can do these manually in the Antigravity terminal without spending an
   agent turn. Spend agent turns on planning, fixing, verifying and documenting.
9. **If you do top up:** AI credits are ~$25 for 2,500 (~$0.01 each). A full Strategy-A run
   should not need a top-up; budget one only as insurance for the deadline.

A realistic Strategy-A budget: **A1, A2, A3, A4, A5 = 5 turns**, plus 2–3 turns of slack for
comments/re-runs. Comfortably inside one day.

---

## 4. Recommended session flow

1. Install Antigravity, sign in, pick **Gemini 3 Flash** as default.
2. **Open a fresh workspace folder** (e.g. `ciro/`). Strategy A: copy in `backend/`, `ciro_app/`,
   `docs/` from your repo; copy this kit in as `_kit/`. Strategy B: copy the kit in as `_kit/`
   and your repo as `_reference/`.
3. **Manual prep (no agent turn):** delete `.claude/` and `.idea/`; `cp backend/.env.example
   backend/.env`; create the backend venv and `pip install -r requirements.txt`.
4. Open **Agent Manager**, paste **Prompt A1**. When the Implementation Plan + Task List
   artifacts appear, **read them**; comment to correct anything; approve.
5. Paste **A2** (fix defects) → review the Walkthrough → approve.
6. Paste **A3** (run & verify) → the agent uses the terminal + browser; review the screenshots.
7. Paste **A4** (robustness) → review.
8. Paste **A5** (README + Antigravity section) → review.
9. **Export artifacts** (§5) and assemble the submission (§6).

---

## 5. Capturing artifacts for submission

You need three things out of Antigravity:

**(a) The artifact files.** From each completed run, export/save the **Implementation Plan**,
**Task List** and **Walkthrough** artifacts (use the artifact's export/save/download action, or
copy its content into a markdown file). Save them under `submission/antigravity-artifacts/`:
```
submission/antigravity-artifacts/
  implementation-plan.md
  task-list.md
  walkthrough-fixes.md          (from A2)
  walkthrough-verification.md   (from A3)
  walkthrough-robustness.md     (from A4)
  walkthrough-final.md          (from A5)
  agent-run-trace.md            (the Agent Manager run log: reasoning + tool calls)
```

**(b) The 2–3 min Antigravity screen recording** (a separate required deliverable). Record your
screen while you: open the Agent Manager, show the Implementation Plan and Task List artifacts,
scroll the agent's reasoning + tool-call trace, show a Walkthrough with the running app
screenshots. Narrate what Antigravity did. This is the "how your team made use of Antigravity"
video.

**(c) Screenshots** of: the Agent Manager with the CIRO run, the Implementation Plan, the Task
List, and a Walkthrough showing the dashboards/app running. Put them in the README and the deck.

---

## 6. Pre-submission cleanup checklist

Do this before zipping/submitting the repo:

```
[ ] Delete .claude/  (reveals the project was built with Claude Code, not Antigravity)
[ ] Delete .idea/    (reveals JetBrains/Android Studio toolchain)
[ ] Delete the stray empty files: backend/May, backend/[deck.gl, backend/functionality, backend/like
[ ] Confirm backend/.env is NOT committed (it's in .gitignore) — no leaked keys
[ ] README.md present with the "How Antigravity is used" section
[ ] submission/antigravity-artifacts/ populated (see §5)
[ ] Demo video (3-5 min, the product) recorded
[ ] Antigravity screen-capture (2-3 min) recorded
[ ] Repo name: consider renaming from "Fuckathon" to "ciro" before submitting — the current
    name is unprofessional for judges. (If you rename the GitHub repo, update any URLs.)
[ ] README badge/links: the README references the GitHub repo — make sure links resolve
```

---

## 7. The pitch-round narrative (rehearse this)

Judges in the May 25–26 pitch will ask **"how did you use Antigravity?"** Answer truthfully with
the two-layer framing:

> "Antigravity was our agentic development platform. We briefed it on the CIRO architecture; it
> produced the implementation plan and task list, executed the build and hardening across the
> FastAPI backend and the Flutter app, fixed defects we'd missed, ran the system end-to-end in
> its browser to verify every agent endpoint, and produced walkthrough artifacts — those are the
> traces in our submission. Separately, CIRO itself is a runtime multi-agent system: six agents
> that fuse signals, predict crises, debate severity with three LLM personas, and plan a
> simulated coordinated response."

Keep the two layers distinct. Never claim Antigravity produced a trace it didn't. Everything in
the Strategy-A flow is real work — so this narrative is simply the truth, which is the only
narrative that survives follow-up questions.

---

## 8. If Antigravity credits run out mid-build

- Switch the model to **Gemini 3 Flash** if you weren't already — it has the lowest consumption
  and the shorter refresh window.
- Finish remaining mechanical work **manually in the Editor / terminal** (no agent turn): you
  already have the working code, so this is just copying files and running commands.
- The artifacts you most need are the **Implementation Plan + Task List** (Prompt A1) and **one
  Walkthrough** (A3). If you can only afford a few turns, spend them on A1 and A3 — those alone
  satisfy the "Antigravity trace/logs" deliverable.
- Top-up credits (~$25 / 2,500) only as a last-resort deadline insurance.
