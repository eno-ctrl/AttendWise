"""
test_calculator.py - Test suite for calculator.py

Run this test suite using:
    pytest test_calculator.py
or
    python -m pytest test_calculator.py -v
"""

import math

import pytest

from calculator import (
    calculate_percentage,
    classes_needed_to_reach_target,
    classes_can_miss,
)


# =====================================================================
# 1. Primary User Story Example (28 attended out of 40, target 75%)
# =====================================================================

def test_primary_example_28_out_of_40():
    """
    Python class example from user story:
    - 40 classes held
    - 28 attended (70%)
    - Target: 75%
    - Must attend 8 consecutive classes: (28 + 8) / (40 + 8) = 36 / 48 = 75%
    - Cannot miss any classes (0 missable)
    """
    attended = 28
    total = 40
    target = 75.0

    percentage = calculate_percentage(attended, total)
    assert percentage == 70.0

    needed = classes_needed_to_reach_target(attended, total, target)
    assert needed == 8

    missable = classes_can_miss(attended, total, target)
    assert missable == 0


# =====================================================================
# 2. Students Below Target
# =====================================================================

def test_student_below_target():
    """
    Test various scenarios where a student is below target:
    - 10 attended out of 20 (50%), target 70%:
      Numerator = 70*20 - 100*10 = 1400 - 1000 = 400
      Denominator = 100 - 70 = 30
      400 / 30 = 13.333 -> ceil is 14 classes needed.
      With 14 classes: (10 + 14) / (20 + 14) = 24 / 34 = 70.59% >= 70%
    """
    attended = 10
    total = 20
    target = 70.0

    assert calculate_percentage(attended, total) == 50.0
    assert classes_needed_to_reach_target(attended, total, target) == 14
    assert classes_can_miss(attended, total, target) == 0


def test_student_barely_below_target():
    """
    Test when student is just 1 class away from target.
    29 attended out of 40 (72.5%), target 75%:
    Numerator = 75*40 - 2900 = 3000 - 2900 = 100
    100 / 25 = 4 classes needed.
    Verification: (29 + 4) / (40 + 4) = 33 / 44 = 75.0%
    """
    assert classes_needed_to_reach_target(29, 40, 75.0) == 4
    assert classes_can_miss(29, 40, 75.0) == 0


# =====================================================================
# 3. Students Exactly At Target
# =====================================================================

def test_student_exactly_at_target():
    """
    When attendance exactly equals the target:
    - 30 attended out of 40 (75.0%), target 75%:
      Needs 0 additional classes.
      Can miss 0 classes (missing 1 would drop it to 30/41 = 73.17%).
    """
    attended = 30
    total = 40
    target = 75.0

    assert calculate_percentage(attended, total) == 75.0
    assert classes_needed_to_reach_target(attended, total, target) == 0
    assert classes_can_miss(attended, total, target) == 0


# =====================================================================
# 4. Students Above Target
# =====================================================================

def test_student_above_target():
    """
    When attendance is above target:
    - 32 attended out of 40 (80%), target 75%:
      Needs 0 additional classes.
      Can miss 2 classes:
        Miss 2: 32 / 42 = 76.19% >= 75% (OK)
        Miss 3: 32 / 43 = 74.41% < 75% (Falls below target)
      Therefore, exactly 2 classes can be missed.
    """
    attended = 32
    total = 40
    target = 75.0

    assert calculate_percentage(attended, total) == 80.0
    assert classes_needed_to_reach_target(attended, total, target) == 0
    assert classes_can_miss(attended, total, target) == 2


def test_student_high_attendance_missable_classes():
    """
    30 attended out of 30 (100%), target 75%:
    Numerator = 100*30 - 75*30 = 3000 - 2250 = 750
    750 / 75 = 10 classes can be missed.
    Verification:
      30 / (30 + 10) = 30 / 40 = 75% (Still >= 75%)
      30 / 41 = 73.17% (Below 75%)
    """
    assert classes_needed_to_reach_target(30, 30, 75.0) == 0
    assert classes_can_miss(30, 30, 75.0) == 10


# =====================================================================
# 5. Zero Classes and Zero Attendance (Edge Case)
# =====================================================================

def test_zero_classes_zero_attendance():
    """
    Semester just started, 0 classes conducted, 0 attended:
    - calculate_percentage should return None (unrecorded attendance, avoids division by zero).
    - classes_needed_to_reach_target should return 0 (no missed classes / no deficit).
    - classes_can_miss should return 0 (cannot afford to miss any upcoming class).
    """
    assert calculate_percentage(0, 0) is None
    assert classes_needed_to_reach_target(0, 0, 75.0) == 0
    assert classes_can_miss(0, 0, 75.0) == 0


# =====================================================================
# 6. Target is 100% (Edge Case)
# =====================================================================

def test_target_100_percent_perfect_attendance():
    """
    Target is 100% and student has attended all classes:
    - 20 attended out of 20 (100%):
      Needs 0 classes.
      Can miss 0 classes (any absence drops below 100%).
    """
    assert calculate_percentage(20, 20) == 100.0
    assert classes_needed_to_reach_target(20, 20, 100.0) == 0
    assert classes_can_miss(20, 20, 100.0) == 0


def test_target_100_percent_impossible_after_miss():
    """
    Target is 100%, but student has missed at least one class:
    - 19 attended out of 20 (95%):
      It is mathematically impossible to reach 100% in a finite number of classes.
      Should return float('inf').
      Can miss 0 classes.
    """
    needed = classes_needed_to_reach_target(19, 20, 100.0)
    assert math.isinf(needed)
    assert needed > 0
    assert classes_can_miss(19, 20, 100.0) == 0


# =====================================================================
# 7. Validation and Invalid Input Handling
# =====================================================================

def test_reject_negative_classes():
    """Negative attended or total counts must raise ValueError."""
    with pytest.raises(ValueError, match="cannot be negative"):
        calculate_percentage(-1, 10)

    with pytest.raises(ValueError, match="cannot be negative"):
        calculate_percentage(5, -10)

    with pytest.raises(ValueError, match="cannot be negative"):
        classes_needed_to_reach_target(-5, 10, 75.0)

    with pytest.raises(ValueError, match="cannot be negative"):
        classes_can_miss(5, -10, 75.0)


def test_reject_attended_greater_than_total():
    """Attended cannot be greater than total conducted classes."""
    with pytest.raises(ValueError, match="cannot exceed total"):
        calculate_percentage(15, 10)

    with pytest.raises(ValueError, match="cannot exceed total"):
        classes_needed_to_reach_target(25, 20, 75.0)

    with pytest.raises(ValueError, match="cannot exceed total"):
        classes_can_miss(30, 20, 75.0)


def test_reject_invalid_targets():
    """Targets must be > 0 and <= 100."""
    # Target 0 or negative
    with pytest.raises(ValueError, match="greater than 0 and at most 100"):
        classes_needed_to_reach_target(20, 30, 0.0)

    with pytest.raises(ValueError, match="greater than 0 and at most 100"):
        classes_needed_to_reach_target(20, 30, -10.0)

    with pytest.raises(ValueError, match="greater than 0 and at most 100"):
        classes_can_miss(20, 30, 0.0)

    # Target greater than 100%
    with pytest.raises(ValueError, match="greater than 0 and at most 100"):
        classes_needed_to_reach_target(20, 30, 101.0)

    with pytest.raises(ValueError, match="greater than 0 and at most 100"):
        classes_can_miss(20, 30, 100.1)


# =====================================================================
# 8. Display Rounding Does Not Corrupt Calculation
# =====================================================================

def test_display_rounding():
    """
    Verify rounding for display in calculate_percentage:
    1 attended out of 3 = 33.33333...% -> rounds to 33.33
    2 attended out of 3 = 66.66666...% -> rounds to 66.67
    """
    assert calculate_percentage(1, 3) == 33.33
    assert calculate_percentage(2, 3) == 66.67
    assert calculate_percentage(1, 3, round_digits=1) == 33.3
