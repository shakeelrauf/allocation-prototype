"""CLI simulator for event streams and allocation demo."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

from allocation_engine import allocate_spaces, rank_users
from event_processor import process_event, seed_users
from models import BehaviorEvent, EventType, UserProfile
from store import InMemoryStore, ScoreStore


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def _open_store(db_path: str | None) -> ScoreStore:
    if db_path:
        from sqlite_store import SqliteStore

        return SqliteStore(db_path)
    return InMemoryStore()


def _seed_if_json(store: ScoreStore, users_json: str | None) -> None:
    if not users_json:
        return
    raw = json.loads(users_json)
    profiles = [
        UserProfile(
            str(u["user_id"]),
            str(u.get("group_id", "default")),
            group_priority=int(u.get("group_priority", 100)),
            user_priority=int(u.get("user_priority", 100)),
        )
        for u in raw
    ]
    seed_users(store, profiles)


def cmd_demo(args: argparse.Namespace) -> None:
    store = _open_store(args.db)
    profiles = [
        UserProfile("alice", "eng", group_priority=1, user_priority=5),
        UserProfile("bob", "eng", group_priority=1, user_priority=5),
        UserProfile("carol", "sales", group_priority=2, user_priority=1),
    ]
    seed_users(store, profiles)

    stream = [
        BehaviorEvent(EventType.CARPOOL_DETECTED, "alice"),
        BehaviorEvent(EventType.UNUSED_BOOKING, "bob"),
        BehaviorEvent(EventType.OFFENCE_REPORTED, "carol"),
        BehaviorEvent(EventType.WEEKLY_DECAY, "bob", payload={"weeks": 2}),
    ]
    for ev in stream:
        r = process_event(store, ev)
        print(r)

    ranked = rank_users(store, ["alice", "bob", "carol"], seed=42)
    for row in ranked:
        print(row.explain)

    winners = allocate_spaces(store, ["alice", "bob", "carol"], capacity=2, seed=42)
    print("allocated:", [w.user_id for w in winners])


def cmd_event(args: argparse.Namespace) -> None:
    store = _open_store(args.db)
    _seed_if_json(store, args.users_json)

    ev = BehaviorEvent(
        args.type,
        args.user_id,
        timestamp=_parse_iso(args.timestamp),
        payload=json.loads(args.payload_json or "{}"),
    )
    r = process_event(store, ev)
    print(json.dumps({"applied": r.applied, "detail": r.detail, "score": r.score_after}))


def cmd_rank(args: argparse.Namespace) -> None:
    store = _open_store(args.db)
    _seed_if_json(store, args.users_json)
    for path in args.events_file:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                ev = BehaviorEvent(
                    obj["event_type"],
                    obj["user_id"],
                    timestamp=_parse_iso(obj.get("timestamp")),
                    payload=obj.get("payload") or {},
                )
                process_event(store, ev)

    ranked = rank_users(store, args.user_ids.split(","), seed=args.seed)
    for row in ranked:
        print(json.dumps({"rank": row.rank, "user_id": row.user_id, "explain": row.explain}))


def cmd_stream(args: argparse.Namespace) -> None:
    """Process NDJSON events line-by-line (stdin or file); optional SQLite persistence."""
    store = _open_store(args.db)
    _seed_if_json(store, args.users_json)

    def _run(lines):
        for line in lines:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            ev = BehaviorEvent(
                obj["event_type"],
                obj["user_id"],
                timestamp=_parse_iso(obj.get("timestamp")),
                payload=obj.get("payload") or {},
            )
            r = process_event(store, ev)
            print(
                json.dumps(
                    {
                        "event_type": r.event_type,
                        "applied": r.applied,
                        "detail": r.detail,
                        "score": r.score_after,
                    }
                )
            )

    if args.events_file:
        with open(args.events_file, encoding="utf-8") as f:
            _run(f)
    else:
        _run(sys.stdin)

    close = getattr(store, "close", None)
    if callable(close):
        close()


def cmd_local_llm(args: argparse.Namespace) -> None:
    """Probe Ollama (GET /api/tags) and print Newton ``NEWTON3_LLM_*`` shell exports."""
    base = args.base_url.rstrip("/")
    tags_url = f"{base}/api/tags"
    try:
        req = urllib.request.Request(tags_url)
        with urllib.request.urlopen(req, timeout=args.timeout) as resp:
            raw = resp.read().decode()
    except urllib.error.URLError as e:
        print(f"Cannot reach Ollama at {base}: {e.reason}", file=sys.stderr)
        print("Tip: ./scripts/setup_local_llm.sh docker", file=sys.stderr)
        raise SystemExit(1) from e
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = {}
    models = payload.get("models") if isinstance(payload, dict) else None
    print(f"OK: reachable at {base}")
    if isinstance(models, list):
        names = [m.get("name", "?") for m in models if isinstance(m, dict)]
        if names:
            print("Installed models:", ", ".join(names[:12]) + ("..." if len(names) > 12 else ""))
    print()
    print("# Paste into your shell before python run_local.py:")
    print(f'export NEWTON3_LLM_URL="{base}/v1/chat/completions"')
    print(f'export NEWTON3_LLM_MODEL="{args.model}"')


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="newton3")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("demo", help="Run built-in scenario")
    d.add_argument("--db", default=None, help="SQLite path (optional)")
    d.set_defaults(func=cmd_demo)

    pe = sub.add_parser("event", help="Process a single event (fresh store)")
    pe.add_argument("type", help="event type string")
    pe.add_argument("user_id")
    pe.add_argument("--timestamp", default=None)
    pe.add_argument("--payload-json", default="{}")
    pe.add_argument("--users-json", default=None, help='optional JSON list of user profiles')
    pe.add_argument("--db", default=None, help="SQLite path (optional)")
    pe.set_defaults(func=cmd_event)

    pr = sub.add_parser("rank", help="Load users + NDJSON events, print ranking")
    pr.add_argument("--users-json", required=True, help='JSON list of user profiles')
    pr.add_argument("--user-ids", required=True, help="comma-separated ids to rank")
    pr.add_argument("--events-file", action="append", default=[], help="NDJSON events (repeatable)")
    pr.add_argument("--seed", type=int, default=None)
    pr.add_argument("--db", default=None, help="SQLite path (optional)")
    pr.set_defaults(func=cmd_rank)

    ps = sub.add_parser("stream", help="Simulate event stream (NDJSON lines from file or stdin)")
    ps.add_argument("--users-json", default=None)
    ps.add_argument("--db", default=None, help="SQLite path (optional)")
    ps.add_argument(
        "events_file",
        nargs="?",
        default=None,
        help="NDJSON file (omit to read stdin)",
    )
    ps.set_defaults(func=cmd_stream)

    pll = sub.add_parser(
        "local-llm",
        help="Check local Ollama and print NEWTON3_LLM_* exports",
    )
    pll.add_argument(
        "--base-url",
        default="http://127.0.0.1:11434",
        help="Ollama HTTP API base (default: http://127.0.0.1:11434)",
    )
    pll.add_argument(
        "--model",
        default="llama3.2",
        help="Model tag Newton should send (must be pulled in Ollama)",
    )
    pll.add_argument("--timeout", type=float, default=5.0, help="Probe timeout seconds")
    pll.set_defaults(func=cmd_local_llm)

    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
