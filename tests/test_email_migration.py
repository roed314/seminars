import ast
import copy
import types
import unittest
from contextlib import nullcontext
from pathlib import Path


MAIN_PATH = Path(__file__).resolve().parents[1] / "seminars" / "users" / "pwdmanager.py"


class EmailNotValidError(Exception):
    pass


def load_table_save():
    source = MAIN_PATH.read_text()
    module = ast.parse(source)
    target = None
    for node in ast.walk(module):
        if isinstance(node, ast.ClassDef) and node.name == "PostgresUserTable":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "save":
                    target = copy.deepcopy(item)
                    target.decorator_list = []
        if target is not None:
            break
    assert target is not None, "PostgresUserTable.save not found"
    mini = ast.Module(body=[target], type_ignores=[])

    calls = []

    class TableStub:
        def __init__(self, name):
            self._name = name

        def update(self, query, changes, **kwargs):
            calls.append((self._name, copy.deepcopy(query), copy.deepcopy(changes)))

    db = types.SimpleNamespace(
        institutions=TableStub("institutions"),
        seminars=TableStub("seminars"),
        seminar_organizers=TableStub("seminar_organizers"),
        talks=TableStub("talks"),
    )
    flashed = []

    def fake_update(self, query, changes, **kwargs):
        calls.append(("users", copy.deepcopy(query), copy.deepcopy(changes)))

    fake_self = types.SimpleNamespace(
        search_cols=["email", "name", "affiliation", "homepage", "timezone"],
        lookup=lambda email: {"email": email, "name": "Old"},
        user_exists=lambda email: False,
        update=fake_update.__get__(types.SimpleNamespace()),
    )
    ns = {
        "db": db,
        "DelayCommit": lambda *a, **k: nullcontext(),
        "validate_email": lambda email: {"email": email},
        "ilike_query": lambda email: {"email": email},
        "EmailNotValidError": EmailNotValidError,
        "flash_error": lambda *a: flashed.append(a),
    }
    exec(compile(mini, str(MAIN_PATH), "exec"), ns)
    return ns["save"].__get__(fake_self), calls, flashed


class EmailMigrationTests(unittest.TestCase):
    def test_email_change_migrates_all_tables(self):
        save, calls, _ = load_table_save()
        old, new = "old@example.edu", "new@example.edu"
        self.assertTrue(save({"email": old, "new_email": new, "name": "New"}))
        by_table = {}
        for table, query, changes in calls:
            by_table.setdefault(table, []).append((query, changes))
        # users row itself moves to the new address
        self.assertIn("users", by_table)
        # every organizer/owner/admin/speaker reference must follow (#933)
        for table, old_col, new_col in [
            ("institutions", "admin", "admin"),
            ("seminars", "owner", "owner"),
            ("seminar_organizers", "email", "email"),
            ("talks", "speaker_email", "speaker_email"),
        ]:
            self.assertIn(table, by_table, f"{table} not updated on email change")
            queries = [q for q, _ in by_table[table]]
            changes = [c for _, c in by_table[table]]
            self.assertTrue(
                any(old in str(q) for q in queries),
                f"{table} update not keyed by old email",
            )
            self.assertTrue(
                any(c.get(new_col) == new for c in changes),
                f"{table} update does not set {new_col} to new email",
            )

    def test_no_change_no_migration_needed(self):
        save, calls, _ = load_table_save()
        # same address in, no new_email: users update still runs, which is
        # fine (old == new, a no-op for the other tables)
        self.assertTrue(save({"email": "same@example.edu", "name": "Same"}))
        self.assertTrue(any(t == "users" for t, _, _ in calls))


if __name__ == "__main__":
    unittest.main()
