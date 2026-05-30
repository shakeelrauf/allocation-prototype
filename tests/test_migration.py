"""Rails CSV migration — dry run and in-memory load (inline CSV, no repo fixtures)."""

from pathlib import Path

from newton3.persistence.store import InMemoryStore
from scripts.migrate_from_rails_export import run_migration


def _write_migration_dir(tmp: Path) -> Path:
    d = tmp / "migration"
    d.mkdir()
    (d / "groups.csv").write_text("group_id,group_priority\neng,1\n", encoding="utf-8")
    (d / "users.csv").write_text(
        "user_id,group_id,group_priority,user_priority\nalice,eng,1,5\nbob,eng,1,8\n",
        encoding="utf-8",
    )
    (d / "events.csv").write_text(
        "event_type,user_id,timestamp,payload_json\n"
        "booking.created,alice,,\n"
        "unused_booking,bob,,\n",
        encoding="utf-8",
    )
    return d


def test_migration_inline_users_and_events(tmp_path):
    store = InMemoryStore()
    audit = run_migration(store, _write_migration_dir(tmp_path), replay_events=True)
    assert audit.users == 2
    assert audit.groups >= 1
    assert audit.events_applied >= 1
    assert store.get_profile("alice") is not None
