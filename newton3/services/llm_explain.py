"""Optional allocation narrative via **Ollama** (local), **Amazon Bedrock** (AWS), or template.

**AWS:** set ``NEWTON3_LLM_BACKEND=bedrock`` and ``NEWTON3_BEDROCK_MODEL_ID`` (Console Lambda in SAM).
Uses the Bedrock **Converse** API (``boto3`` ``bedrock-runtime``). Enable the model in the Bedrock
console for your region before deploy.

**Local:** Ollama auto-detect or ``NEWTON3_LLM_URL`` (unchanged when Bedrock env is not set).

---

Optional allocation narrative via **Ollama** (local), or a deterministic template.

Pull models from https://ollama.com/library. Ollama exposes chat at ``/v1/chat/completions``.
Quick start from repo root::

    ./scripts/setup_local_llm.sh install-ollama   # then: ./scripts/setup_local_llm.sh native
    ./scripts/setup_local_llm.sh docker         # if Docker is installed
    python -m cli local-llm                # prints export NEWTON3_LLM_URL=...

Then use Explain & AI → chat-style narrative in the UI.

Multi-turn chat: POST ``messages`` as prior ``user`` / ``assistant`` turns (max 48), plus
``follow_up`` for the next user message; the server always refreshes the ranking from
``user_ids`` / ``seed`` and injects it into that turn.

If ``NEWTON3_LLM_URL`` is unset, Newton **probes** ``http://127.0.0.1:11434/api/tags``
once per process (when ``NEWTON3_LLM_AUTO`` is not ``0``). If Ollama answers, the API uses
``http://127.0.0.1:11434/v1/chat/completions`` automatically — no exports needed for typical
local runs. Set ``NEWTON3_LLM_AUTO=0`` on hosts where localhost must never be contacted.
Override the probe host with ``NEWTON3_OLLAMA_HOST`` (default ``127.0.0.1``).

Optional: ``NEWTON3_LLM_TEMPERATURE`` (default ``0.25``) is sent to Ollama/OpenAI-compatible APIs.

Optional: ``NEWTON3_LLM_CHARACTER_NAME`` (default ``Shakeel``) sets the assistant persona name in the system prompt.

Optional: ``NEWTON3_LLM_ALLOC_CAPACITY`` (default ``10``) caps how many winning spots appear in the allocation
block of the store snapshot when the client does not send ``allocation_capacity``.

Snapshot size (prompt tokens) for faster LLM calls, especially in Docker without GPU — tune with
``NEWTON3_LLM_SNAPSHOT_EVENTS_LOOKBACK`` (default ``180``) and ``NEWTON3_LLM_SNAPSHOT_MAX_EVENT_LINES``
(default ``100``).

Optional: ``NEWTON3_LLM_KEEP_ALIVE`` (e.g. ``15m`` or ``-1``) is passed to Ollama’s chat payload so the model
stays loaded between requests (fewer long cold starts after idle).

Ollama requests always set ``"stream": false`` so the server returns one JSON body (compatible with
blocking ``urlopen``).
"""

from __future__ import annotations

import json
import os
from typing import Any, Iterable

from newton3.domain.allocation_engine import allocate_spaces
from newton3.domain.models import BehaviorEvent, tier_for_score
from newton3.persistence.store import ScoreStore
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

_DEFAULT_OLLAMA_HOST = os.environ.get("NEWTON3_OLLAMA_HOST", "127.0.0.1").strip() or "127.0.0.1"


def _env_int(name: str, default: int, lo: int, hi: int) -> int:
    try:
        v = int((os.environ.get(name) or str(default)).strip())
    except ValueError:
        return default
    return max(lo, min(hi, v))


def _llm_character_name() -> str:
    return (os.environ.get("NEWTON3_LLM_CHARACTER_NAME") or "Shakeel").strip() or "Shakeel"


def _build_system_prompt() -> str:
    n = _llm_character_name()
    return f"""You are {n}, Newton 3’s friendly parking-allocation guide for facility and workplace teams.
Stay in this voice: warm, concise, professional — like a helpful colleague, not a robot or a legal brief.

You explain rankings in plain Markdown (short paragraphs or bullets). Greet or acknowledge the user naturally when it fits (e.g. if they say hi).

Never output JSON, curly braces, or keys like "title" / "summary" / "bullets". Never wrap answers in ``` code blocks unless showing a tiny example unrelated to the ranking.

Use facts from the user's ranking lines and any **Newton data snapshot** block (groups, profiles, events, allocation). Do not invent data outside those sections. Correct precedence is: lower group_priority first, then lower user_priority, then higher behaviour_score, then lower tie_breaker."""

_MAX_CHAT_TURNS = 48

_NEWTON_SORT_RULES = (
    "Order (best rank first): lower group_priority, then lower user_priority, "
    "then higher behaviour_score, then lower tie_breaker (0–1 for this seed)."
)

_MARKDOWN_ONLY_TAIL = "Answer in plain Markdown only — not JSON or `{...}` objects."


def _looks_like_json_narrative_blob(s: str) -> bool:
    """Detect models that reply with a faux-report JSON object instead of prose."""
    t = s.lstrip()
    if not t.startswith("{"):
        return False
    head = t[:1800].lower()
    return any(k in head for k in ('"title"', '"summary"', '"bullets"', '"rank_notes"', '"fairness"'))


def _coerce_markdown_reply(raw: str, template_md: str) -> str:
    """If the model ignored instructions and dumped JSON-shaped text, show the template instead."""
    if not _looks_like_json_narrative_blob(raw):
        return raw
    return (
        "_The model replied with JSON-style text instead of Markdown. "
        "Here is Newton’s deterministic summary:_\n\n" + template_md
    )
_auto_probe_done = False
_auto_probe_url: str | None = None


def _reset_llm_auto_probe() -> None:
    """Clear cached Ollama probe (used by tests via conftest)."""
    global _auto_probe_done, _auto_probe_url
    _auto_probe_done = False
    _auto_probe_url = None


def _llm_backend_mode() -> str:
    return (os.environ.get("NEWTON3_LLM_BACKEND") or "auto").strip().lower()


def _bedrock_model_id() -> str:
    return (os.environ.get("NEWTON3_BEDROCK_MODEL_ID") or "").strip()


def bedrock_configured() -> bool:
    """True when Bedrock Converse should be used (AWS Console Lambda)."""
    mode = _llm_backend_mode()
    model = _bedrock_model_id()
    if mode in ("bedrock", "aws"):
        return bool(model)
    if mode == "auto" and model:
        return True
    return False


def _bedrock_region() -> str:
    explicit = (os.environ.get("NEWTON3_BEDROCK_REGION") or "").strip()
    if explicit:
        return explicit
    return (
        os.environ.get("AWS_REGION")
        or os.environ.get("AWS_DEFAULT_REGION")
        or "eu-west-1"
    )


def _messages_for_bedrock_converse(
    messages: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], list[dict[str, str]] | None]:
    """Split system prompt from user/assistant turns for Converse API."""
    system_blocks: list[dict[str, str]] = []
    converse_messages: list[dict[str, Any]] = []
    for m in messages:
        role = (m.get("role") or "user").strip()
        content = str(m.get("content") or "")
        if role == "system":
            system_blocks.append({"text": content})
        elif role in ("user", "assistant"):
            converse_messages.append({"role": role, "content": [{"text": content}]})
    system = system_blocks or None
    return converse_messages, system


def _post_bedrock_converse(
    messages: list[dict[str, str]],
    *,
    max_tokens: int = 400,
    temperature: float = 0.25,
    timeout: float = 120.0,
) -> str:
    """Call Amazon Bedrock Converse API (requires IAM on Lambda)."""
    model_id = _bedrock_model_id()
    if not model_id:
        raise RuntimeError("NEWTON3_BEDROCK_MODEL_ID is not set")

    try:
        import boto3
        from botocore.config import Config
    except ImportError as e:
        raise RuntimeError("boto3 is required for Bedrock backend") from e

    region = _bedrock_region()
    cfg = Config(
        read_timeout=max(int(timeout), 30),
        connect_timeout=15,
        retries={"max_attempts": 2},
    )
    client = boto3.client("bedrock-runtime", region_name=region, config=cfg)
    converse_messages, system = _messages_for_bedrock_converse(messages)
    if not converse_messages:
        raise RuntimeError("No user/assistant messages for Bedrock")

    kwargs: dict[str, Any] = {
        "modelId": model_id,
        "messages": converse_messages,
        "inferenceConfig": {
            "maxTokens": max(64, min(max_tokens, 4096)),
            "temperature": max(0.0, min(2.0, temperature)),
        },
    }
    if system:
        kwargs["system"] = system

    try:
        response = client.converse(**kwargs)
    except Exception as e:
        raise RuntimeError(f"Bedrock Converse failed: {e}") from e

    try:
        for block in response["output"]["message"]["content"]:
            if isinstance(block, dict) and block.get("text"):
                return str(block["text"])
    except (KeyError, TypeError) as e:
        raise RuntimeError(f"Unexpected Bedrock response: {response!r}") from e
    raise RuntimeError(f"Bedrock returned no text: {response!r}")


def _llm_auto_enabled() -> bool:
    if bedrock_configured():
        return False
    raw = os.environ.get("NEWTON3_LLM_AUTO", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _detect_local_ollama_chat_url() -> str | None:
    """Return Ollama chat-completions URL if ``/api/tags`` responds (cached once per process).

    Call only when ``NEWTON3_LLM_URL`` is unset; never pollutes cache when only explicit
    URL was set elsewhere so ``/api/health`` cannot block later auto-detection.
    """
    global _auto_probe_done, _auto_probe_url
    if not _llm_auto_enabled():
        return None
    if _auto_probe_done:
        return _auto_probe_url
    _auto_probe_done = True
    tags = f"http://{_DEFAULT_OLLAMA_HOST}:11434/api/tags"
    try:
        req = Request(tags)
        with urlopen(req, timeout=0.85) as resp:
            resp.read(65536)
        chat = f"http://{_DEFAULT_OLLAMA_HOST}:11434/v1/chat/completions"
        _auto_probe_url = chat
        return chat
    except Exception:
        _auto_probe_url = None
        return None


def template_explanation(ranking: list[dict[str, Any]]) -> str:
    """Deterministic baseline judges can read without Ollama."""
    lines = []
    for row in ranking:
        lines.append(f"Rank {row.get('rank')}: **{row.get('user_id')}** — {row.get('explain', '')}")
    return (
        "### Allocation summary (Newton 3)\n\n"
        + "\n".join(lines)
        + "\n\n_Sorting: lower group priority → lower user priority → higher behaviour score → lower tie-breaker "
        "(deterministic for a fixed seed)._"
    )


def _ranking_lines(ranking: Iterable[dict[str, Any]]) -> list[str]:
    return [f"{r.get('rank')}. {r.get('user_id')}: {r.get('explain')}" for r in ranking]


def _snapshot_event_line(ev: BehaviorEvent) -> str:
    et = getattr(ev.event_type, "value", ev.event_type)
    ts = ev.timestamp.isoformat() if ev.timestamp else ""
    try:
        pj = json.dumps(ev.payload or {}, ensure_ascii=False, default=str)[:160]
    except TypeError:
        pj = str(ev.payload)[:160]
    return f"- {ts} | {et} | user={ev.user_id} | {pj}"


def gather_llm_store_snapshot(
    store: ScoreStore,
    pool_ids: list[str],
    *,
    seed: int | None = None,
    allocation_capacity: int | None = None,
    events_lookback: int | None = None,
    max_event_lines: int | None = None,
) -> str:
    """Compact Markdown-ish lines: groups, pool profiles/scores, recent events, allocation winners."""
    if events_lookback is None:
        events_lookback = _env_int("NEWTON3_LLM_SNAPSHOT_EVENTS_LOOKBACK", 180, 5, 5000)
    if max_event_lines is None:
        max_event_lines = _env_int("NEWTON3_LLM_SNAPSHOT_MAX_EVENT_LINES", 100, 3, 500)
    rows: list[str] = []
    pool_set = set(pool_ids)
    n = len(pool_ids)

    if hasattr(store, "list_groups") and callable(getattr(store, "list_groups")):
        try:
            groups = store.list_groups()
            rows.append("**Groups** (group_priority — lower wins across groups)")
            for g in groups:
                gid = g.get("group_id", "?")
                gp = g.get("group_priority", "?")
                rows.append(f"- {gid}: group_priority={gp}")
            rows.append("")
        except Exception:
            rows.append("(Groups registry unavailable.)")
            rows.append("")

    rows.append("**Pool users** (profiles + current behaviour score)")
    for uid in pool_ids:
        prof = store.get_profile(uid)
        if prof is None:
            rows.append(f"- {uid}: not registered in store")
            continue
        sc = store.get_score_state(uid)
        tier = tier_for_score(sc.score).value
        rows.append(
            f"- {uid}: group_id={prof.group_id} group_priority={prof.group_priority} "
            f"user_priority={prof.user_priority} behaviour_score={sc.score:.2f} tier={tier}"
        )
    rows.append("")

    rows.append(f"**Recent events** (up to {events_lookback} log lines; pool users listed first)")
    evs = store.recent_events(events_lookback)
    pool_first = [e for e in evs if e.user_id in pool_set]
    other = [e for e in evs if e.user_id not in pool_set]
    merged = pool_first + other
    if not merged:
        rows.append("(No events logged.)")
    else:
        for ev in merged[:max_event_lines]:
            rows.append(_snapshot_event_line(ev))
        if len(merged) > max_event_lines:
            rows.append(f"... ({len(merged) - max_event_lines} more lines omitted)")
    rows.append("")

    if allocation_capacity is None:
        try:
            cap_default = int(os.environ.get("NEWTON3_LLM_ALLOC_CAPACITY", "10").strip())
        except ValueError:
            cap_default = 10
        cap_default = max(1, min(cap_default, 500))
        cap = max(1, min(n, cap_default)) if n else 1
    else:
        cap = max(1, min(int(allocation_capacity), n)) if n else 1

    rows.append(f"**Space allocation** (Newton `allocate_spaces`, capacity={cap}, same seed as ranking)")
    if not pool_ids:
        rows.append("(Empty pool.)")
    else:
        winners = allocate_spaces(store, pool_ids, capacity=cap, seed=seed)
        for w in winners:
            rows.append(f"- Spot #{w.rank}: {w.user_id} — {w.explain}")

    return "\n".join(rows)


def _build_initial_user_prompt(
    ranking: list[dict[str, Any]],
    context: str,
    *,
    store_snapshot: str = "",
) -> str:
    parts = ["Explain this parking allocation ranking briefly for a facility manager."]
    if context.strip():
        parts.append(context.strip())
    parts.append(_NEWTON_SORT_RULES)
    parts.append(_MARKDOWN_ONLY_TAIL)
    parts.append("")
    parts.extend(_ranking_lines(ranking))
    if store_snapshot.strip():
        parts.extend(["", "### Newton data snapshot", store_snapshot.strip()])
    return "\n".join(parts)


def _build_follow_up_user_prompt(
    ranking: list[dict[str, Any]],
    follow_up: str,
    *,
    store_snapshot: str = "",
) -> str:
    lines = "\n".join(_ranking_lines(ranking))
    q = follow_up.strip() or "Elaborate briefly."
    snap = ""
    if store_snapshot.strip():
        snap = f"\n\n### Newton data snapshot\n{store_snapshot.strip()}"
    return f"{_NEWTON_SORT_RULES}\n\n{lines}{snap}\n\nFollow-up:\n{q}\n\n{_MARKDOWN_ONLY_TAIL}"


def _sanitize_chat_messages(messages: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Keep only user/assistant string pairs; trim tail to ``_MAX_CHAT_TURNS``."""
    out: list[dict[str, str]] = []
    for m in messages:
        role = m.get("role")
        raw = m.get("content")
        if role not in ("user", "assistant") or not isinstance(raw, str):
            continue
        content = raw.strip()
        if not content:
            continue
        out.append({"role": str(role), "content": content})
    if len(out) > _MAX_CHAT_TURNS:
        out = out[-_MAX_CHAT_TURNS:]
    return out


def _post_ollama_chat(
    url: str,
    model: str,
    messages: list[dict[str, str]],
    *,
    bearer: str | None,
    max_tokens: int = 400,
    timeout: float = 120.0,
    temperature: float = 0.25,
) -> str:
    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": max(0.0, min(2.0, temperature)),
        "stream": False,
    }
    keep = (os.environ.get("NEWTON3_LLM_KEEP_ALIVE") or "").strip()
    if keep:
        # Ollama extension; keeps model resident to avoid multi-minute reload between chats.
        try:
            body["keep_alive"] = int(keep)
        except ValueError:
            body["keep_alive"] = keep
    num_ctx_raw = (os.environ.get("NEWTON3_LLM_NUM_CTX") or "").strip()
    if num_ctx_raw:
        try:
            nctx = int(num_ctx_raw)
            if 256 <= nctx <= 131072:
                body["options"] = {"num_ctx": nctx}
        except ValueError:
            pass
    payload = json.dumps(body).encode()
    headers = {"Content-Type": "application/json"}
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    req = Request(url, data=payload, headers=headers, method="POST")
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = json.loads(resp.read().decode())
    except HTTPError as e:
        body = e.read().decode(errors="replace") if e.fp else ""
        raise RuntimeError(f"LLM HTTP {e.code}: {body or e.reason}") from e
    except URLError as e:
        raise RuntimeError(f"LLM connection failed: {e.reason}") from e
    try:
        return raw["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise RuntimeError(f"Unexpected LLM response shape: {raw!r}") from e


def enrich_with_llm(
    ranking: list[dict[str, Any]],
    *,
    context: str = "",
    messages: list[dict[str, Any]] | None = None,
    follow_up: str | None = None,
    store_snapshot: str = "",
) -> dict[str, Any]:
    """
    Try Ollama with optional multi-turn history (ChatGPT-style payload):

    - Empty ``messages``: single turn; user content = initial explanation request + ``context``.
    - Non-empty ``messages``: prior ``user`` / ``assistant`` turns only; new user content =
      refreshed ranking snapshot + ``follow_up``.

    Backend resolution:
    1. ``NEWTON3_LLM_URL`` if set, else auto-detected ``…/v1/chat/completions`` on
       ``NEWTON3_OLLAMA_HOST`` (unless ``NEWTON3_LLM_AUTO=0``).
    2. Otherwise template-only markdown summary.

    Every response includes ``echo_user``: the exact user message appended this request
    (for UI transcript sync).
    """
    base = template_explanation(ranking)
    hist = _sanitize_chat_messages(messages or [])
    snap = store_snapshot.strip()
    if not hist:
        user_content = _build_initial_user_prompt(ranking, context, store_snapshot=snap)
    else:
        user_content = _build_follow_up_user_prompt(ranking, follow_up or "", store_snapshot=snap)

    full_messages: list[dict[str, str]] = (
        [{"role": "system", "content": _build_system_prompt()}] + hist + [{"role": "user", "content": user_content}]
    )

    try:
        max_tok = int(os.environ.get("NEWTON3_LLM_MAX_TOKENS", "400"))
    except ValueError:
        max_tok = 400
    try:
        timeout = float(os.environ.get("NEWTON3_LLM_TIMEOUT", "120"))
    except ValueError:
        timeout = 120.0
    try:
        temp_raw = os.environ.get("NEWTON3_LLM_TEMPERATURE", "0.25").strip()
        llm_temperature = float(temp_raw)
    except ValueError:
        llm_temperature = 0.25
    token_cap = max(64, min(max_tok, 4096))

    if bedrock_configured():
        try:
            text = _post_bedrock_converse(
                full_messages,
                max_tokens=token_cap,
                timeout=timeout,
                temperature=llm_temperature,
            )
            text = _coerce_markdown_reply(text, base)
            return {
                "mode": "bedrock",
                "text": text,
                "template_fallback": base,
                "llm_source": "bedrock",
                "llm_model": _bedrock_model_id(),
                "llm_region": _bedrock_region(),
                "echo_user": user_content,
            }
        except Exception as e:
            return {"mode": "error", "error": str(e), "text": base, "echo_user": user_content}

    chat_url = os.environ.get("NEWTON3_LLM_URL", "").strip()
    if not chat_url:
        chat_url = _detect_local_ollama_chat_url() or ""

    if chat_url:
        model = (os.environ.get("NEWTON3_LLM_MODEL") or "llama3.2").strip() or "llama3.2"
        api_key = os.environ.get("NEWTON3_LLM_API_KEY", "").strip() or None
        try:
            text = _post_ollama_chat(
                chat_url,
                model,
                full_messages,
                bearer=api_key,
                max_tokens=token_cap,
                timeout=timeout,
                temperature=llm_temperature,
            )
            text = _coerce_markdown_reply(text, base)
            src = "env" if os.environ.get("NEWTON3_LLM_URL", "").strip() else "auto"
            return {
                "mode": "ollama",
                "text": text,
                "template_fallback": base,
                "llm_source": src,
                "echo_user": user_content,
            }
        except Exception as e:
            return {"mode": "error", "error": str(e), "text": base, "echo_user": user_content}

    parts = [
        "Ollama not reachable. Start Ollama or set NEWTON3_LLM_URL to its chat endpoint "
        f"(e.g. http://{_DEFAULT_OLLAMA_HOST}:11434/v1/chat/completions).",
    ]
    if _llm_auto_enabled():
        parts.append(
            f"Auto-detect tried http://{_DEFAULT_OLLAMA_HOST}:11434 (NEWTON3_LLM_AUTO=1)."
        )
    else:
        parts.append(
            "NEWTON3_LLM_AUTO=0 disables localhost probing; set NEWTON3_LLM_URL explicitly."
        )
    return {"mode": "template", "text": base, "hint": " ".join(parts), "echo_user": user_content}


def llm_feature_flags() -> dict[str, Any]:
    """For /api/health: LLM backend availability (Bedrock on AWS, Ollama locally)."""
    if bedrock_configured():
        return {
            "llm_explain_env": True,
            "llm_backend": "bedrock",
            "llm_auto_ollama": False,
            "llm_bedrock_model": _bedrock_model_id(),
            "llm_bedrock_region": _bedrock_region(),
            "llm_character": _llm_character_name(),
        }
    explicit = bool(os.environ.get("NEWTON3_LLM_URL", "").strip())
    auto_hit = bool(not explicit and _detect_local_ollama_chat_url())
    ollama_on = explicit or auto_hit
    backend = "ollama" if ollama_on else "off"
    return {
        "llm_explain_env": ollama_on,
        "llm_backend": backend,
        "llm_auto_ollama": auto_hit,
        "llm_character": _llm_character_name(),
    }
