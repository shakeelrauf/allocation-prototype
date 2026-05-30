# Deploy Newton 3 on AWS (SAM)

Use **your own AWS account** (Free Tier is sufficient). Region recommendation: `eu-west-1` (aligns with Wayleadr EU).

**Architecture context:** [AWS_SERVERLESS_ARCHITECTURE.md](./AWS_SERVERLESS_ARCHITECTURE.md). Local development stays on **SQLite** via `run_local.py`.

**Deployed hybrid stack:**

| Component | Role |
|-----------|------|
| **Console Lambda (Mangum)** | Full `/api/*` operator API (users, events, reports, admin) via `ANY /{proxy+}` |
| **Read Lambda** | Fast `GET /api/health`, WayID `GET .../behavior-score` |
| **Allocation Lambda** | `GET /api/allocation/*` (rank, allocate, shadow, explain) |
| **Scoring Lambda** | Consumes **SQS** (penalties/rewards); weekly decay via schedule |
| **EventBridge → SQS** | External producers (`newton3.booking`, etc.) |
| **DynamoDB** | Five tables (on-demand) |
| **Amazon Bedrock** | Explain & AI via Console Lambda (`POST /api/allocation/explain-llm`) |

HTTP `POST /api/events` from the UI stays **synchronous** (`NEWTON3_EVENTS_HTTP_SYNC=true`) so score deltas return immediately. EventBridge traffic is **async** via SQS.

**LLM:** AWS uses **Bedrock Converse** (default Claude 3.5 Haiku). Local dev still uses **Ollama** — no Bedrock env vars needed.

## Prerequisites

- AWS CLI configured (`aws sts get-caller-identity`)
- [SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html) 1.100+
- Python 3.11 (for local migration script only)

## 1. Build and deploy

```bash
cd infra/sam
cp samconfig.toml.example samconfig.toml
# Edit region/stack if needed

sam build
sam deploy --guided
```

Guided prompts:

- Stack name: `newton3-dev`
- Region: `eu-west-1`
- Confirm IAM capabilities: **Y**

Note the outputs **`HttpApiUrl`** and **`BedrockModelId`**.

SAM parameters (guided deploy or `samconfig.toml`):

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `BedrockModelId` | `anthropic.claude-3-5-haiku-20241022-v1:0` | Bedrock foundation model for narratives |
| `LlmBackend` | `bedrock` | `bedrock` = enable LLM on Console Lambda; `off` = template-only |

## 1b. Enable Bedrock model access (required once per account/region)

Before Explain & AI works on AWS:

1. Open **Amazon Bedrock** in the same region as deploy (e.g. `eu-west-1`).
2. **Model access** (or **Chat / text playground**) → enable **Anthropic Claude 3.5 Haiku** (or your chosen `BedrockModelId`).
3. Accept any provider terms if prompted.

Console Lambda env (set automatically by SAM when `LlmBackend=bedrock`):

| Variable | Example |
|----------|---------|
| `NEWTON3_LLM_BACKEND` | `bedrock` |
| `NEWTON3_BEDROCK_MODEL_ID` | `anthropic.claude-3-5-haiku-20241022-v1:0` |
| `NEWTON3_LLM_AUTO` | `0` (no localhost Ollama probe on Lambda) |

IAM on **Console Lambda** includes `bedrock:Converse` and `bedrock:InvokeModel` for foundation models in the stack region.

To disable paid LLM calls: deploy with `LlmBackend=off` (template-only explanations).

## 2. Migrate sample data

After deploy, table names follow `newton3-dev-*` (or your `Stage` parameter).

```bash
cd ../..   # repo root
pip install boto3
export AWS_REGION=eu-west-1

python scripts/migrate_from_rails_export.py \
  --backend dynamodb \
  --stage dev \
  --dir fixtures/migration
```

## 3. Smoke test

Replace `BASE` with your `HttpApiUrl` (no trailing slash).

```bash
BASE="https://xxxx.execute-api.eu-west-1.amazonaws.com/dev"

curl -s "$BASE/api/health" | jq .

curl -s -X POST "$BASE/api/events" \
  -H "Content-Type: application/json" \
  -d '{"event_type":"unused_booking","user_id":"bob","payload":{}}' | jq .

curl -s "$BASE/users/alice/behavior-score" | jq .

curl -s "$BASE/api/allocation/rank?user_ids=alice,bob,carol&seed=1" | jq .

curl -s "$BASE/api/allocation/shadow?user_ids=alice,bob,carol&seed=1" | jq .

curl -s "$BASE/api/users" | jq .
curl -s "$BASE/api/events/recent?limit=5" | jq .

# Bedrock LLM (Console Lambda — needs model access + migrated users)
curl -s "$BASE/api/health" | jq '.features.llm_backend, .features.llm_bedrock_model'
curl -s -X POST "$BASE/api/allocation/explain-llm" \
  -H "Content-Type: application/json" \
  -d '{"user_ids":"alice,bob","seed":1,"context":"Why this order?"}' | jq '.mode, .text[:200]'
```

Expect `llm_backend` = `"bedrock"` and explain response `mode` = `"bedrock"` when configured.

Set `AdminEnabled=false` at deploy time to block `/api/admin/*` on the Console Lambda.

## 4. Publish a behaviour event (EventBridge → SQS)

```bash
aws events put-events --entries "[{
  \"EventBusName\": \"newton3-dev-events\",
  \"Source\": \"newton3.booking\",
  \"DetailType\": \"BehaviorEvent\",
  \"Detail\": \"{\\\"event_type\\\":\\\"carpool.detected\\\",\\\"user_id\\\":\\\"alice\\\",\\\"payload\\\":{}}\"
}]"
```

The rule forwards to **`BehaviorEventsQueue`**; the scoring Lambda processes messages within seconds. Check CloudWatch Logs for `newton3-dev-scoring`.

## 5. Shadow validation job

```bash
aws lambda invoke --function-name newton3-dev-shadow-compare \
  --payload '{"user_ids":["alice","bob","carol"],"seed":1}' \
  /tmp/shadow.json && cat /tmp/shadow.json | jq .
```

## 6. Tear down

```bash
cd infra/sam && sam delete --stack-name newton3-dev
```

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `boto3` missing | `pip install boto3` |
| Access denied | Ensure IAM user can create Lambda, DDB, API Gateway |
| Empty behaviour score | Run migration first; user must exist in DDB |
| Cold start latency | Normal on Free Tier; retry once |
| Bedrock `AccessDeniedException` | Enable model in Bedrock console; check region matches deploy |
| `llm_backend` is `off` | Redeploy with `LlmBackend=bedrock` or check Console Lambda env |
| Explain timeout | Console Lambda timeout is 120s; use Haiku or reduce snapshot env vars |

## Cost note

Pay-per-request DynamoDB + Lambda within Free Tier for demo traffic. **Bedrock** is pay-per-token (Haiku is low cost); set `LlmBackend=off` to skip LLM charges. **Local** dev uses Ollama in Docker, not Bedrock.
