"""
test_integration.py - Integration Test Suite for AttendWise

Tests integration between:
1. calculator.py (Math formulas and guidance logic)
2. database.py (SQLite persistence and atomic class updates)
3. main.py (Dashboard aggregation, edge case guidance, and validation)

Run this test suite using:
    pytest test_integration.py -v
or
    python test_integration.py
"""

import os
import math
import tempfile
import pathlib
import contextlib
import importlib

# Dynamic import of pytest for maximum environment flexibility
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

from calculator import (
    calculate_percentage,
    classes_needed_to_reach_target,
    classes_can_miss,
)
from database import (
    init_db,
    add_subject,
    get_all_subjects,
    get_subject_by_id,
    update_subject,
    record_class_status,
    delete_subject,
    DuplicateSubjectError,
    SubjectNotFoundError,
)


@fixture_decorator
def app_db(tmp_path=None):
    """Creates a temporary isolated SQLite database file."""
    if tmp_path is not None:
        db_file = pathlib.Path(tmp_path) / "test_integration.db"
        path_str = str(db_file)
    else:
        temp_dir = tempfile.mkdtemp()
        path_str = os.path.join(temp_dir, "test_integration.db")

    init_db(path_str)
    return path_str


# =====================================================================
# 1. Overall Attendance Aggregation Logic
# =====================================================================

def test_overall_attendance_calculation(app_db):
    """
    Verify overall attendance calculates (sum attended) / (sum total).
    NOT an average of subject percentages!
    Subject 1: 10 / 10 = 100%
    Subject 2: 10 / 30 = 33.33%
    Average of percentages would be (100 + 33.33) / 2 = 66.67% (INCORRECT).
    True overall: (10 + 10) / (10 + 30) = 20 / 40 = 50.0% (CORRECT).
    """
    add_subject(app_db, "Subject A", 10, 10, 75.0)
    add_subject(app_db, "Subject B", 10, 30, 75.0)

    subjects = get_all_subjects(app_db)
    sum_attended = sum(s["attended_classes"] for s in subjects)
    sum_total = sum(s["total_classes"] for s in subjects)

    overall = calculate_percentage(sum_attended, sum_total)
    assert overall == 50.0  # Exactly 50.0%, NOT 66.67%


def test_overall_attendance_zero_classes(app_db):
    """When no classes have been conducted across all subjects, overall must be None."""
    add_subject(app_db, "New Course 1", 0, 0, 75.0)
    add_subject(app_db, "New Course 2", 0, 0, 80.0)

    subjects = get_all_subjects(app_db)
    sum_attended = sum(s["attended_classes"] for s in subjects)
    sum_total = sum(s["total_classes"] for s in subjects)

    overall = calculate_percentage(sum_attended, sum_total)
    assert overall is None


# =====================================================================
# 2. Guidance Logic Across Edge Cases
# =====================================================================

def test_guidance_below_target(app_db):
    """Verify guidance when attendance is below target."""
    sub_id = add_subject(app_db, "Python", 28, 40, 75.0)
    sub = get_subject_by_id(app_db, sub_id)

    needed = classes_needed_to_reach_target(sub["attended_classes"], sub["total_classes"], sub["target_percentage"])
    assert needed == 8

    missable = classes_can_miss(sub["attended_classes"], sub["total_classes"], sub["target_percentage"])
    assert missable == 0


def test_guidance_above_target(app_db):
    """Verify guidance when attendance is above target."""
    sub_id = add_subject(app_db, "Python", 32, 40, 75.0)
    sub = get_subject_by_id(app_db, sub_id)

    needed = classes_needed_to_reach_target(sub["attended_classes"], sub["total_classes"], sub["target_percentage"])
    assert needed == 0

    missable = classes_can_miss(sub["attended_classes"], sub["total_classes"], sub["target_percentage"])
    assert missable == 2


def test_guidance_target_100_percent_impossible(app_db):
    """Target is 100% and student missed 1 class: must return infinity."""
    sub_id = add_subject(app_db, "Perfect Goal", 19, 20, 100.0)
    sub = get_subject_by_id(app_db, sub_id)

    needed = classes_needed_to_reach_target(sub["attended_classes"], sub["total_classes"], sub["target_percentage"])
    assert math.isinf(needed)
    assert needed > 0


# =====================================================================
# 3. Complete Action Workflows (+ Attended, + Missed, Edit, Delete)
# =====================================================================

def test_full_attendance_action_workflow(app_db):
    """
    Test student life cycle:
    1. Start semester at 28/40 (70%, target 75%). Needs 8 classes.
    2. Attends 1 class: becomes 29/41 (70.73%).
    3. Misses 1 class: becomes 29/42 (69.05%).
    4. Edits subject target to 70%.
    5. Deletes subject when finished.
    """
    # 1. Add
    sub_id = add_subject(app_db, "Python", 28, 40, 75.0)
    s = get_subject_by_id(app_db, sub_id)
    assert calculate_percentage(s["attended_classes"], s["total_classes"]) == 70.0
    assert classes_needed_to_reach_target(s["attended_classes"], s["total_classes"], 75.0) == 8

    # 2. + Attended
    s = record_class_status(app_db, sub_id, attended_class=True)
    assert s["attended_classes"] == 29
    assert s["total_classes"] == 41

    # 3. + Missed
    s = record_class_status(app_db, sub_id, attended_class=False)
    assert s["attended_classes"] == 29
    assert s["total_classes"] == 42
    assert calculate_percentage(s["attended_classes"], s["total_classes"]) == 69.05

    # 4. Edit target
    update_subject(app_db, sub_id, "Python Advanced", 29, 42, 70.0)
    s = get_subject_by_id(app_db, sub_id)
    assert s["name"] == "Python Advanced"
    assert s["target_percentage"] == 70.0

    # 5. Delete
    delete_subject(app_db, sub_id)
    assert get_subject_by_id(app_db, sub_id) is None


# =====================================================================
# 4. Data Persistence Across Re-initialization
# =====================================================================

def test_data_persists_across_app_restarts(app_db):
    """Ensure data is intact after closing and reopening database."""
    sub_id = add_subject(app_db, "Machine Learning", 15, 18, 75.0)

    # Re-initialize (simulating app relaunch)
    init_db(app_db)
    subjects = get_all_subjects(app_db)
    assert len(subjects) == 1
    assert subjects[0]["id"] == sub_id
    assert subjects[0]["name"] == "Machine Learning"


# =====================================================================
# Standalone Runner
# =====================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Running AttendWise Integration Test Suite...")
    print("=" * 60)

    test_functions = [
        func for name, func in globals().items()
        if callable(func) and name.startswith("test_")
    ]

    passed = 0
    failed = 0
    for test_fn in test_functions:
        temp_dir = tempfile.TemporaryDirectory()
        db_path = os.path.join(temp_dir.name, "attendwise_integration_test.db")
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
        print(f"SUCCESS: All {passed} integration tests passed successfully!")
    else:
        print(f"FAILURE: {failed} test(s) failed, {passed} passed.")
    print("=" * 60)
