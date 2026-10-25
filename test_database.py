"""
test_database.py - Automated Test Suite for AttendWise Database Layer

Run this test suite using:
    pytest test_database.py -v
or
    python test_database.py
"""

import os
import sqlite3
import tempfile
import pathlib
import contextlib
import importlib

# Resolve pytest dynamically to prevent editor missing-import warnings if pytest is not installed
try:
    pytest = importlib.import_module("pytest")
    fixture_decorator = pytest.fixture
except ImportError:
    class _PytestShim:
        @staticmethod
        def fixture(func):
            return func

        @staticmethod
        @contextlib.contextmanager
        def raises(expected_exception, match=None):
            try:
                yield
            except expected_exception as exc:
                if match and match not in str(exc):
                    raise AssertionError(f"Pattern '{match}' not found in exception message: '{exc}'")
            else:
                raise AssertionError(f"Expected exception {expected_exception.__name__} was not raised.")

    pytest = _PytestShim()
    fixture_decorator = pytest.fixture

from database import (
    init_db,
    add_subject,
    get_all_subjects,
    get_subject_by_id,
    update_subject,
    record_class_status,
    delete_subject,
    get_connection,
    SubjectNotFoundError,
    DuplicateSubjectError,
)


# =====================================================================
# Fixture: Temporary Database File for Each Test
# =====================================================================

@fixture_decorator
def app_db(tmp_path=None):
    """
    Creates a fresh, isolated temporary SQLite database file for a test.
    Supports both pytest's tmp_path fixture and manual standalone execution.
    """
    if tmp_path is not None:
        db_file = pathlib.Path(tmp_path) / "test_attendwise.db"
        path_str = str(db_file)
    else:
        temp_dir = tempfile.mkdtemp()
        path_str = os.path.join(temp_dir, "test_attendwise.db")

    init_db(path_str)
    return path_str


# =====================================================================
# 1. Database Initialization
# =====================================================================

def test_init_db_creates_table(app_db):
    """Verify that init_db creates the subjects table with all required columns."""
    with get_connection(app_db) as conn:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='subjects';"
        )
        assert cursor.fetchone() is not None

        # Verify columns exist
        cursor = conn.execute("PRAGMA table_info(subjects);")
        columns = {row["name"]: row["type"] for row in cursor.fetchall()}
        assert "id" in columns
        assert "name" in columns
        assert "attended_classes" in columns
        assert "total_classes" in columns
        assert "target_percentage" in columns


def test_init_db_is_idempotent(app_db):
    """Calling init_db multiple times on an existing database must not fail or erase data."""
    sub_id = add_subject(app_db, "Python", 28, 40, 75.0)

    # Re-run init_db
    init_db(app_db)
    init_db(app_db)

    # Existing subject must still be present
    subject = get_subject_by_id(app_db, sub_id)
    assert subject is not None
    assert subject["name"] == "Python"
    assert subject["attended_classes"] == 28


# =====================================================================
# 2. Adding and Retrieving Subjects
# =====================================================================

def test_add_and_get_subject_by_id(app_db):
    """Add a subject and verify retrieving it by its generated ID."""
    sub_id = add_subject(app_db, "Mathematics", 18, 20, 80.0)
    assert isinstance(sub_id, int)
    assert sub_id > 0

    subject = get_subject_by_id(app_db, sub_id)
    assert subject is not None
    assert subject["id"] == sub_id
    assert subject["name"] == "Mathematics"
    assert subject["attended_classes"] == 18
    assert subject["total_classes"] == 20
    assert subject["target_percentage"] == 80.0


def test_get_all_subjects_ordered(app_db):
    """Verify get_all_subjects returns all records ordered alphabetically."""
    add_subject(app_db, "Physics", 10, 10, 75.0)
    add_subject(app_db, "Chemistry", 8, 10, 75.0)
    add_subject(app_db, "Biology", 9, 10, 75.0)

    subjects = get_all_subjects(app_db)
    assert len(subjects) == 3
    names = [s["name"] for s in subjects]
    assert names == ["Biology", "Chemistry", "Physics"]


def test_get_nonexistent_subject_id(app_db):
    """Retrieving an ID that does not exist should return None."""
    assert get_subject_by_id(app_db, 9999) is None


# =====================================================================
# 3. Updating and Deleting Subjects
# =====================================================================

def test_update_subject(app_db):
    """Update all fields of an existing subject and verify changes."""
    sub_id = add_subject(app_db, "Python", 28, 40, 75.0)

    update_subject(app_db, sub_id, "Advanced Python", 35, 45, 80.0)

    updated = get_subject_by_id(app_db, sub_id)
    assert updated["name"] == "Advanced Python"
    assert updated["attended_classes"] == 35
    assert updated["total_classes"] == 45
    assert updated["target_percentage"] == 80.0


def test_update_nonexistent_subject_raises_error(app_db):
    """Attempting to update an ID that does not exist must raise SubjectNotFoundError."""
    with pytest.raises(SubjectNotFoundError, match="was not found"):
        update_subject(app_db, 9999, "Ghost Subject", 5, 10, 75.0)


def test_delete_subject(app_db):
    """Delete a subject and verify it is completely removed."""
    sub_id = add_subject(app_db, "History", 10, 12, 70.0)
    assert get_subject_by_id(app_db, sub_id) is not None

    delete_subject(app_db, sub_id)
    assert get_subject_by_id(app_db, sub_id) is None
    assert len(get_all_subjects(app_db)) == 0


def test_delete_nonexistent_subject_raises_error(app_db):
    """Attempting to delete an ID that does not exist must raise SubjectNotFoundError."""
    with pytest.raises(SubjectNotFoundError, match="was not found"):
        delete_subject(app_db, 9999)


# =====================================================================
# 4. Quick Increment: record_class_status
# =====================================================================

def test_record_attended_class(app_db):
    """
    Recording an attended class (+1 present) must increment
    BOTH attended_classes and total_classes.
    """
    sub_id = add_subject(app_db, "Python", 28, 40, 75.0)

    updated = record_class_status(app_db, sub_id, attended_class=True)
    assert updated["attended_classes"] == 29
    assert updated["total_classes"] == 41

    # Verify directly from database
    persisted = get_subject_by_id(app_db, sub_id)
    assert persisted["attended_classes"] == 29
    assert persisted["total_classes"] == 41


def test_record_missed_class(app_db):
    """
    Recording a missed class (absent) must increment
    ONLY total_classes, leaving attended_classes unchanged.
    """
    sub_id = add_subject(app_db, "Python", 28, 40, 75.0)

    updated = record_class_status(app_db, sub_id, attended_class=False)
    assert updated["attended_classes"] == 28
    assert updated["total_classes"] == 41

    persisted = get_subject_by_id(app_db, sub_id)
    assert persisted["attended_classes"] == 28
    assert persisted["total_classes"] == 41


def test_record_class_status_nonexistent_subject(app_db):
    """Recording attendance for a nonexistent ID must raise SubjectNotFoundError."""
    with pytest.raises(SubjectNotFoundError, match="was not found"):
        record_class_status(app_db, 9999, attended_class=True)


# =====================================================================
# 5. Validation and Edge Cases
# =====================================================================

def test_reject_empty_or_whitespace_name(app_db):
    """Reject empty strings or names containing only whitespace."""
    with pytest.raises(ValueError, match="cannot be empty"):
        add_subject(app_db, "")

    with pytest.raises(ValueError, match="cannot be empty"):
        add_subject(app_db, "   ")

    with pytest.raises(ValueError, match="cannot be empty"):
        add_subject(app_db, "\t\n")


def test_whitespace_is_trimmed(app_db):
    """Surrounding whitespace should be trimmed automatically."""
    sub_id = add_subject(app_db, "   Data Structures   ", 5, 5, 75.0)
    subject = get_subject_by_id(app_db, sub_id)
    assert subject["name"] == "Data Structures"


def test_reject_duplicate_names_case_insensitive(app_db):
    """Duplicate names must be rejected, regardless of letter casing."""
    add_subject(app_db, "Python", 10, 10, 75.0)

    # Exact match
    with pytest.raises(DuplicateSubjectError, match="already exists"):
        add_subject(app_db, "Python", 5, 5, 75.0)

    # Lowercase match
    with pytest.raises(DuplicateSubjectError, match="already exists"):
        add_subject(app_db, "python", 5, 5, 75.0)

    # Uppercase match
    with pytest.raises(DuplicateSubjectError, match="already exists"):
        add_subject(app_db, "PYTHON", 5, 5, 75.0)


def test_reject_negative_counts(app_db):
    """Reject negative attended or total counts."""
    with pytest.raises(ValueError, match="cannot be negative"):
        add_subject(app_db, "Subject A", -1, 10, 75.0)

    with pytest.raises(ValueError, match="cannot be negative"):
        add_subject(app_db, "Subject B", 5, -10, 75.0)


def test_reject_attended_exceeding_total(app_db):
    """Reject attended counts greater than total classes."""
    with pytest.raises(ValueError, match="cannot exceed total"):
        add_subject(app_db, "Math", 15, 10, 75.0)


def test_reject_invalid_target_percentages(app_db):
    """Target percentage must be > 0 and <= 100."""
    with pytest.raises(ValueError, match="greater than 0 and at most 100"):
        add_subject(app_db, "Subject Zero", 5, 10, 0.0)

    with pytest.raises(ValueError, match="greater than 0 and at most 100"):
        add_subject(app_db, "Subject Negative", 5, 10, -5.0)

    with pytest.raises(ValueError, match="greater than 0 and at most 100"):
        add_subject(app_db, "Subject Over", 5, 10, 100.5)


def test_reject_invalid_input_types(app_db):
    """Reject incorrect data types (e.g. booleans or strings for numbers)."""
    with pytest.raises(TypeError, match="must be a string"):
        add_subject(app_db, 12345, 5, 10, 75.0)

    with pytest.raises(TypeError, match="must be an integer"):
        add_subject(app_db, "Valid Name", True, 10, 75.0)  # bool rejected

    with pytest.raises(TypeError, match="must be a boolean"):
        record_class_status(app_db, 1, "yes")


# =====================================================================
# 6. Data Integrity and Connection Independence
# =====================================================================

def test_persistence_across_separate_connections(app_db):
    """Verify data written in one connection is safely readable in subsequent connections."""
    sub_id = add_subject(app_db, "Calculus", 20, 25, 80.0)

    # Close and read again through a fresh connection
    subject = get_subject_by_id(app_db, sub_id)
    assert subject is not None
    assert subject["name"] == "Calculus"
    assert subject["attended_classes"] == 20


def test_transaction_rollback_prevents_corruption(app_db):
    """Verify that a failed operation does not corrupt existing data."""
    sub_id = add_subject(app_db, "Operating Systems", 10, 10, 75.0)

    # Attempt an update that violates a database CHECK constraint directly
    try:
        with get_connection(app_db) as conn:
            # attended (15) > total (10) violates SQLite CHECK constraint
            conn.execute(
                "UPDATE subjects SET attended_classes = 15 WHERE id = ?;",
                (sub_id,)
            )
    except sqlite3.IntegrityError:
        pass  # Expected constraint violation

    # The original row must remain intact and uncorrupted
    subject = get_subject_by_id(app_db, sub_id)
    assert subject["attended_classes"] == 10
    assert subject["total_classes"] == 10


# =====================================================================
# Standalone Runner (Allows running with: python test_database.py)
# =====================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Running AttendWise Database Test Suite...")
    print("=" * 60)

    test_functions = [
        func for name, func in globals().items()
        if callable(func) and name.startswith("test_")
    ]

    passed = 0
    failed = 0
    for test_fn in test_functions:
        temp_dir = tempfile.TemporaryDirectory()
        db_path = os.path.join(temp_dir.name, "attendwise_test.db")
        init_db(db_path)
        try:
            test_fn(db_path)
            print(f"  [PASS] {test_fn.__name__}")
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {test_fn.__name__}: {e}")
            failed += 1
        finally:
            temp_dir.cleanup()

    print("-" * 60)
    if failed == 0:
        print(f"SUCCESS: All {passed} database tests passed successfully!")
    else:
        print(f"FAILURE: {failed} test(s) failed, {passed} passed.")
    print("=" * 60)
