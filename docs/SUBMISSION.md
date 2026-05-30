# Newton 3 — Hackathon submission (June 2026)

## Links

| Item | URL |
|------|-----|
| **GitHub (Wayleadr internal)** | https://github.com/wayleadr-internal/shakeel-allocation-prototype |
| **Demo video** | https://www.loom.com/share/d7478cd7208a498cba2b2272b6b4a42c |
| **Architecture** | [ARCHITECTURE.md](../ARCHITECTURE.md) |
| **AWS deploy** | [DEPLOY_AWS.md](./DEPLOY_AWS.md) |
| **Complaint cohort fairness** | [FAIRNESS_COMPLAINT_COHORT.md](./FAIRNESS_COMPLAINT_COHORT.md) |

## One-line pitch

Behaviour-driven parking allocation: **admin priorities preserved**, **fairness via transparent scores**, **AWS-native Phase 1** with migration and shadow validation — plus an explainable demo UI and optional LLM guide.

## Problem

Legacy allocation is hard to explain; users do not see why they lost a space. CS lacks tooling for fairness conversations.

## Solution

1. **Behaviour score** (base 100, penalties/rewards, decay, tiers)  
2. **Newton ranking** — group → user → behaviour → tie-breaker  
3. **Shadow mode** — compare to legacy before cutover  
4. **Migration** — Rails CSV → DynamoDB (no prod dependency)  
5. **Explainability** — per-user rank narrative + optional Ollama LLM  

## Demo video (Loom)

[Watch the walkthrough](https://www.loom.com/share/d7478cd7208a498cba2b2272b6b4a42c) — import Metabase CSV directly in the UI, then behaviour events, allocation, explain/shadow, insights, and fairness reporting.

## What works today

- ✅ 40 automated tests (`pytest`)  
- ✅ Docker one-command demo (UI + API + SQLite + Ollama)  
- ✅ AWS SAM stack (Lambda + DynamoDB + API Gateway + EventBridge)  
- ✅ Migration script + sample fixtures  
- ✅ Fairness CSV report, tenant weights, insights heuristics  

## AWS-native (hackathon requirement)

Deploy to **your AWS account** (Free Tier):

```bash
cd infra/sam && sam build && sam deploy --guided
```

Then migrate sample data and call `GET /users/{id}/behavior-score` on the deployed URL.

Full steps: [DEPLOY_AWS.md](./DEPLOY_AWS.md).

## Alignment with Wayleadr 2.0

| Initiative | How this project supports it |
|------------|------------------------------|
| AWS platform | SAM, DynamoDB, EventBridge, Lambda |
| WayID | `GET /users/{id}/behavior-score` contract |
| Newton 3 | Allocation engine + shadow comparator |
| Phase 1 migration | `scripts/migrate_from_rails_export.py` |
| No Rails runtime | Standalone service |

## Reviewer quick start (Bruno: no local run required)

1. Watch [Loom demo](https://www.loom.com/share/d7478cd7208a498cba2b2272b6b4a42c) (CSV import + full UI).  
2. Skim [ARCHITECTURE.md](../ARCHITECTURE.md) (10 min).  
3. Browse `tests/` for scenario coverage.  
4. Optional: deploy SAM using DEPLOY_AWS (screenshot API response in PR description).

## Slides

**Full deck source for PowerPoint:** [SLIDES_FOR_PPT.md](./SLIDES_FOR_PPT.md) — legacy vs Newton, behaviour score, screenshots, tech stack, local + AWS, speaker notes.  
Short outline: [SLIDES_OUTLINE.md](./SLIDES_OUTLINE.md).

## Team / compliance

- No Wayleadr credentials or customer data in repo.  
- Sample CSVs are synthetic.  
- AWS account: submitter’s own (Free Tier).

## Known Phase 2 items (documented, not hidden)

- Early-cancel **+5 reward** (customer story) — passive `booking.cancelled` today  
- Post–big-allocation **score reset** — `reset_cycle()` exists; wire on allocate flag  
- Full Rails extractor job — CSV contract documented; replace with anonymized export pipeline  
