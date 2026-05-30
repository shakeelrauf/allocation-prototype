# Newton 3 Hackathon — CLAUDE.md

## Context

You are helping to build **Newton 3.0**, a next-generation allocation engine for Wayleadr.

This is a **hackathon project** (May 1 → Jun 1 submission) aimed at shaping the production future of how Wayleadr makes allocation decisions.

The goal is not incremental improvement — it's a reimagining of allocation that is:

- **Transparent** — decisions should be explainable
- **Fair** — behaviour-driven, not opaque rules
- **Scalable** — AWS-native, AI-ready architecture

This system:

- Replaces a legacy Rails-based allocation system
- Is fully **AWS-native and serverless** (local: SQLite + FastAPI)
- Uses a **behaviour-driven scoring model**
- Must be implemented in **Python**

**Important:** You do NOT need to understand the legacy Rails system in depth. Focus on the **target system in Python**. **No Rails dependency. No legacy coupling.**

**Repo layout:** see [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md).

---

## Hackathon goals

Build a **working prototype** judges evaluate on:

1. How well the solution works in practice
2. How many scenarios/functions it handles
3. Simplicity and scalability of the approach

**Core deliverables:**

1. Behaviour Scoring Engine → `newton3/domain/scoring_engine.py`
2. Allocation Engine → `newton3/domain/allocation_engine.py`
3. Event-driven architecture → `newton3/domain/event_processor.py`, `newton3/services/events_queue.py`, AWS EventBridge + SQS

**Stretch goals (implemented or partial):**

- AI-assisted explanation → `newton3/services/llm_explain.py`
- Dynamic weight configuration per tenant → `newton3/domain/tenant_weights.py`
- Shadow mode comparator → `newton3/domain/shadow_engine.py`
- Explainability layer → allocation explain + LLM
- Admin/CS dashboard → `ui/` + `newton3/api/app.py`

---

## Core concepts

### Behaviour score

Each user starts with `base_score = 100`.

```
score = base_score + rewards - penalties + decay
```

| Type | Points |
|------|--------|
| Unused booking (no-show) | −3 |
| Free space / non-paid usage | −1 |
| Offence | −5 |
| Carpool | +5 |
| Weekly decay | +2/week toward base (capped at 100) |

**Constraints:** min score 0; reward cap +20 rolling 4 weeks.

**Tiers:** Platinum 150+, Gold 120–149, Silver 80–119, Bronze 50–79, Restricted &lt;50.

### Allocation sort key

```python
(group_priority, user_priority, -behavior_score, tie_breaker)
```

---

## Event-driven model

| Event | Score impact |
|-------|----------------|
| `booking.created` / `cancelled` / `completed` | None (Phase 1) |
| `gate.entry_detected` | Logged |
| `offence.reported` | −5 |
| `carpool.detected` | +5 (capped) |
| `unused_booking` | −3 |
| `free_space_used` | −1 |
| `weekly_decay` | +2 (capped) |

**Local:** `POST /api/events` → synchronous `process_event`. Ollama for Explain & AI.  
**AWS:** EventBridge → SQS → scoring Lambda; **Amazon Bedrock** (Claude Haiku) for Explain & AI on Console Lambda.

---

## Where code lives (not flat root)

```
newton3/                 # Python package
  domain/               # scoring, allocation, events, fairness
  persistence/          # store, sqlite, dynamodb, factory
  services/             # events_queue, cohort_import, llm_explain
  api/app.py            # FastAPI
run_local.py            # local server entrypoint
cli.py                  # CLI shim
aws/handlers/           # Lambda entrypoints
tests/
ui/
infra/sam/
```

---

## How to use Claude on this repo

**Do:**

- Change domain logic under `newton3/domain/`
- Keep Lambdas thin in `aws/handlers/`
- Run `pytest` and `python run_local.py --reload`
- Propose AI/fairness improvements aligned with the spec

**Do not:**

- Depend on Rails
- Duplicate business rules in handlers
- Put new modules loose on repo root — use the package layout

---

## Success criteria

- Working Python implementation with clear separation of concerns
- Correct event-driven scoring and explainable allocation
- Edge cases: min score, reward cap, decay, restricted tier
- Local SQLite demo + AWS SAM deploy path
- Bonus: LLM explain, shadow compare, fairness cohort

---

## Timeline

| Date | Milestone |
|------|-----------|
| May 1 | Kick-off |
| Jun 1 | Submission |
| Jun 11 | Results |

**Rewards:** €1,000 Winner · €500 Runner-up

---

Let's build the future of Wayleadr allocation.
