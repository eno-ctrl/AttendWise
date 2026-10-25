"""
calculator.py - AttendWise Calculation Engine

This module handles all the core attendance calculations for the AttendWise app.
It provides functions to:
1. Calculate attendance percentage.
2. Determine how many consecutive classes you must attend to reach a goal.
3. Determine how many classes you can safely miss without dropping below your goal.
"""

import math
from typing import Optional, Union


def calculate_percentage(
    attended_classes: int,
    total_classes: int,
    round_digits: int = 2
) -> Optional[float]:
    """
    Calculates the attendance percentage.

    Parameters:
        attended_classes (int): Number of classes the student attended.
        total_classes (int): Total number of classes conducted.
        round_digits (int): Decimal places to round the final percentage for display (default is 2).

    Returns:
        float: The attendance percentage (e.g., 70.0 for 70%).
        None: If total_classes is 0, representing unrecorded attendance (no classes held yet).

    Raises:
        ValueError: If class counts are negative, or if attended exceeds total.
    """
    # 1. Validation: Reject negative numbers
    if attended_classes < 0 or total_classes < 0:
        raise ValueError("Class counts cannot be negative.")

    # 2. Validation: Attended cannot be greater than total
    if attended_classes > total_classes:
        raise ValueError("Attended classes cannot exceed total classes.")

    # 3. Handle zero classes: Avoid division by zero
    if total_classes == 0:
        return None

    # 4. Calculation: (attended / total) * 100
    raw_percentage = (attended_classes / total_classes) * 100.0
    return round(raw_percentage, round_digits)


def classes_needed_to_reach_target(
    attended_classes: int,
    total_classes: int,
    target_percentage: float
) -> Union[int, float]:
    """
    Calculates how many consecutive classes a student must attend to reach their target percentage.

    Parameters:
        attended_classes (int): Number of classes attended so far.
        total_classes (int): Total classes conducted so far.
        target_percentage (float): Desired attendance percentage (must be > 0 and <= 100).

    Returns:
        int: Number of consecutive classes to attend. Returns 0 if already at or above target.
        float: Returns float('inf') if reaching the target is impossible (e.g., 100% target after missing a class).

    Raises:
        ValueError: For invalid class counts or targets outside the range (0, 100].
    """
    # 1. Validation
    if attended_classes < 0 or total_classes < 0:
        raise ValueError("Class counts cannot be negative.")
    if attended_classes > total_classes:
        raise ValueError("Attended classes cannot exceed total classes.")
    if target_percentage <= 0 or target_percentage > 100:
        raise ValueError("Target percentage must be greater than 0 and at most 100.")

    # 2. Zero classes held: No classes missed, so no makeup classes are needed
    if total_classes == 0:
        return 0

    # 3. Check if already meeting or exceeding target
    current_percentage = (attended_classes / total_classes) * 100.0
    if current_percentage >= target_percentage:
        return 0

    # 4. Special Case: Target is 100%
    # If target is 100% and the student has missed even one class,
    # reaching 100% in a finite number of classes is mathematically impossible.
    if target_percentage == 100.0:
        return float('inf')

    # 5. Formula derivation for target < 100%:
    # (attended + x) / (total + x) >= target / 100
    # attended + x >= (target / 100) * (total + x)
    # x * (1 - target / 100) >= (target / 100) * total - attended
    # Multiply by 100 on both sides:
    # x * (100 - target) >= target * total - 100 * attended
    # x >= (target * total - 100 * attended) / (100 - target)
    numerator = (target_percentage * total_classes) - (100.0 * attended_classes)
    denominator = 100.0 - target_percentage

    # Use ceiling because attending a partial class is not possible
    classes_needed = math.ceil(numerator / denominator)

    # Ensure we never return a negative number
    return max(0, classes_needed)


def classes_can_miss(
    attended_classes: int,
    total_classes: int,
    target_percentage: float
) -> int:
    """
    Calculates the maximum number of upcoming classes a student can miss without falling
    below their target percentage.

    Parameters:
        attended_classes (int): Number of classes attended so far.
        total_classes (int): Total classes conducted so far.
        target_percentage (float): Desired attendance percentage (must be > 0 and <= 100).

    Returns:
        int: Maximum number of classes that can be missed. Returns 0 if already below or at target,
             or if no classes have occurred yet.

    Raises:
        ValueError: For invalid class counts or targets outside the range (0, 100].
    """
    # 1. Validation
    if attended_classes < 0 or total_classes < 0:
        raise ValueError("Class counts cannot be negative.")
    if attended_classes > total_classes:
        raise ValueError("Attended classes cannot exceed total classes.")
    if target_percentage <= 0 or target_percentage > 100:
        raise ValueError("Target percentage must be greater than 0 and at most 100.")

    # 2. If no classes held yet, student cannot afford to miss any upcoming class
    if total_classes == 0:
        return 0

    # 3. If currently below the target, 0 classes can be missed
    current_percentage = (attended_classes / total_classes) * 100.0
    if current_percentage < target_percentage:
        return 0

    # 4. Formula derivation:
    # attended / (total + y) >= target / 100
    # attended * 100 >= target * (total + y)
    # target * y <= 100 * attended - target * total
    # y <= (100 * attended - target * total) / target
    numerator = (100.0 * attended_classes) - (target_percentage * total_classes)
    denominator = target_percentage

    # Use floor because missing any more would drop attendance below target
    missable = math.floor(numerator / denominator)

    # Ensure we never return a negative number
    return max(0, missable)
