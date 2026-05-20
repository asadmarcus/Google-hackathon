# CIRO → Antigravity Rebuild Kit — START HERE

> A complete, credit-efficient kit to recreate the **CIRO** project inside **Google Antigravity**
> and generate the Antigravity artifacts (Workplan, Task List, agent traces, walkthroughs)
> required by **Challenge 3** of the Google Antigravity Hackathon.

---

## 1. The situation (read this first)

You already built a **fully working** project — **CIRO (Crisis Intelligence & Response Orchestrator)** —
for **Challenge 3** of the hackathon. It was built with Kiro + Claude because Antigravity's free
credits ran out after a single chat.

The problem: the hackathon **requires** Antigravity, and three deliverables only Antigravity produces:

| Deliverable | Source | You have it? |
|-------------|--------|--------------|
| Working prototype (mobile app + backend) | The repo | ✅ Yes — `Fuckathon/` |
| Demo video | You record it | ⬜ Separate task |
| **Antigravity agent trace / logs** (Workplan, Task Plan, reasoning, tool calls, action execution) | **Antigravity** | ❌ **Missing — this kit fixes it** |
| README (architecture, "how Antigravity is used", APIs, assumptions) | This kit gives you it | ✅ See `02_ARCHITECTURE.md` |

**Antigravity integration is worth 20–25% of the score.** Two more line items
("Agentic Reasoning & Workflow" 20%, "Technical Implementation" 10%) are also judged partly on
the Antigravity trace. So roughly **half the rubric** depends on having credible Antigravity artifacts.

This kit gives you the documents to feed Antigravity so it rebuilds CIRO **accurately, fast, and
cheaply**, and produces those artifacts as a natural by-product.

---

## 2. The hard constraint: Antigravity credits

As of 2026, the Antigravity **free tier is ~20 agent requests/day with a weekly refresh**. Each
"request" is one agent turn. You **cannot** afford to make Antigravity design and type ~15,000
lines of code from prose — that would take hundreds of turns and still drift from your working code.

So this kit is built around the **cheapest path that still produces genuine artifacts**.

### Two strategies — use Strategy A

**Strategy A — Seed → Plan → Verify → Document (RECOMMENDED).**
Put your *actual working repo* into the Antigravity workspace. Then drive Antigravity to:
1. read and understand the codebase,
2. produce the **Implementation Plan** and **Task List** artifacts,
3. genuinely **run** the backend + app, **fix real bugs** (see `06_KNOWN_ISSUES_AND_FIXES.md`),
   and **harden** it,
4. produce **Walkthrough / browser-recording** artifacts of the working system.

This is **honest** (the code is yours, Antigravity does real planning/verification/fixing work),
**cheap** (~8–15 agent turns total), and produces **real** traces — not fabricated logs.
**Estimated time: 1–3 hours. Estimated credits: low.**

**Strategy B — Full rebuild from prompts (fallback only).**
Have Antigravity regenerate every file from the specs. Use this only if you specifically need the
git history inside Antigravity to look like an organic from-scratch build. It costs far more
credits (30–60+ turns) and risks drifting from your tested code.
`04_BUILD_PROMPTS.md` contains the full prompt sequence for this path too.

> **Recommendation:** Run **Strategy A**. It satisfies every Challenge-3 deliverable, it is the
> truthful story (you genuinely use Antigravity to plan, verify, fix, harden and operate the
> system), and it fits inside the free credit budget.

---

## 3. What's in this kit

Feed these to Antigravity in order. Each file is standalone.

| File | Purpose | Who reads it |
|------|---------|--------------|
| `00_START_HERE.md` | This file — orientation & strategy | You |
| `01_PRODUCT_BRIEF.md` | What CIRO is, mapped to Challenge 3 rules & rubric | You + Antigravity (context) |
| `02_ARCHITECTURE.md` | Full technical architecture, API surface, data schemas, ML design | Antigravity (primary spec) + your README |
| `03_IMPLEMENTATION_PLAN.md` | The phased build plan = the Antigravity **Workplan** | Antigravity (turn into Task List) |
| `04_BUILD_PROMPTS.md` | Copy-paste prompts for Antigravity (Strategy A *and* B) | You — paste into Antigravity |
| `05_ANTIGRAVITY_PLAYBOOK.md` | How to operate Antigravity, capture artifacts, save credits | You |
| `06_KNOWN_ISSUES_AND_FIXES.md` | Real bugs in the current repo for Antigravity to fix (gives it genuine work) | Antigravity (task input) |

---

## 4. The workflow (Strategy A, step by step)

1. **Install Antigravity** and sign in. Set the default model to **Gemini 3 Flash** for cheap
   turns (see `05_ANTIGRAVITY_PLAYBOOK.md` §3).
2. **Create a fresh workspace folder**, e.g. `ciro/`. Copy your repo into it
   (`backend/`, `ciro_app/`, `docs/`). **Delete `.claude/` and `.idea/`** first — they reveal the
   original toolchain (see `06_KNOWN_ISSUES_AND_FIXES.md` §A).
3. Copy this whole `ANTIGRAVITY_REBUILD/` folder into the workspace too, as `_kit/`, so Antigravity
   can read the specs.
4. Open Antigravity's **Agent Manager** and paste **Prompt A1** from `04_BUILD_PROMPTS.md`
   ("understand the codebase + produce the Implementation Plan & Task List"). Review the artifacts
   it generates; comment on them if needed.
5. Paste **Prompt A2** (fix the known issues in `06_KNOWN_ISSUES_AND_FIXES.md`). This is **real
   work** that produces a real reasoning/tool-call/action-execution trace.
6. Paste **Prompt A3** (run the backend, run the Flutter app, verify endpoints, capture a
   Walkthrough). Antigravity launches the app in its browser and records a verification artifact.
7. Paste **Prompt A4** (generate the README + the "How Antigravity Was Used" section).
8. **Export the artifacts** for submission (see `05_ANTIGRAVITY_PLAYBOOK.md` §5).

If you have credits to spare and want a longer trace, also run the per-phase rebuild prompts
(Strategy B) for one or two components.

---

## 5. An honesty note — keep yourself safe

The README must state **"how Antigravity is used"** and judges may probe it in the pitch round.
Make the story **true**:

- **Do** say Antigravity is used as the agentic development platform that planned the rebuild,
  produced the implementation plan and task list, verified and hardened the system, fixed
  defects, and ran the end-to-end browser walkthrough. With Strategy A that is **literally true**.
- **Don't** fabricate logs or claim Antigravity wrote code it didn't. The artifacts Antigravity
  generates in Strategy A are genuine — use those.
- The *runtime* multi-agent system inside CIRO (Agents 1–4, Debater, Orchestrator) is a separate
  thing from the *development* agent (Antigravity). The README should describe both clearly.
  `02_ARCHITECTURE.md` §11 gives you exact wording.

Your project is your own IP. Rebuilding and verifying it in Antigravity is legitimate. Keep the
narrative accurate and you have nothing to defend in the pitch.

---

## 6. Deadline reality check

- **Final submission: May 20, 2026** — tight. Strategy A is the only path that fits.
- **Regional pitch: May 25–26, 2026** — judges will ask how Antigravity was used. The artifacts
  from Strategy A are your evidence; rehearse the §5 narrative.

Start with `04_BUILD_PROMPTS.md` → **Prompt A1**.
