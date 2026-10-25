"""
database.py - AttendWise SQLite Database Layer

This module manages permanent data storage for the AttendWise application using
Python's built-in sqlite3 library.

Key Features:
- Explicit db_path parameter for all operations (clean, predictable, testable).
- Guaranteed connection cleanup and transaction rollback via context manager.
- Parameterized SQL queries to prevent SQL injection.
- Case-insensitive duplicate prevention using COLLATE NOCASE.
- Database-level and Python-level constraint validations.
"""

import sqlite3
import contextlib
from typing import Optional, List, Dict, Any


# =====================================================================
# Custom Exceptions
# =====================================================================

class AttendWiseDBError(Exception):
    """Base exception for AttendWise database operations."""
    pass


class SubjectNotFoundError(AttendWiseDBError):
    """Raised when an operation targets a subject ID that does not exist."""
    pass


class DuplicateSubjectError(AttendWiseDBError):
    """Raised when adding or renaming to a subject name that already exists."""
    pass


# =====================================================================
# Connection Management Helper
# =====================================================================

@contextlib.contextmanager
def get_connection(db_path: str):
    """
    Context manager for SQLite database connections.

    Why this design is safe and robust:
    1. 'with conn:' handles TRANSACTIONS (commits on success, rolls back on error).
    2. 'finally: conn.close()' guarantees the database connection is closed,
       even if an unhandled exception or crash occurs.
    3. 'conn.row_factory = sqlite3.Row' allows rows to be accessed like dictionaries.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    # Enable foreign keys and foreign key constraints in SQLite
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        with conn:
            yield conn
    finally:
        conn.close()


# =====================================================================
# Input Validation Helper
# =====================================================================

def _validate_subject_inputs(
    name: str,
    attended_classes: int,
    total_classes: int,
    target_percentage: float
) -> str:
    """
    Validates input types and values before executing any database operation.
    Returns the cleaned (stripped) subject name.
    """
    # 1. Validate subject name
    if not isinstance(name, str):
        raise TypeError("Subject name must be a string.")
    
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("Subject name cannot be empty or blank.")

    # 2. Validate class counts
    # In Python, bool is a subclass of int (isinstance(True, int) is True),
    # so we explicitly reject booleans for numeric counts.
    if isinstance(attended_classes, bool) or not isinstance(attended_classes, int):
        raise TypeError("Attended classes must be an integer.")
    if isinstance(total_classes, bool) or not isinstance(total_classes, int):
        raise TypeError("Total classes must be an integer.")

    if attended_classes < 0 or total_classes < 0:
        raise ValueError("Class counts cannot be negative.")
    if attended_classes > total_classes:
        raise ValueError("Attended classes cannot exceed total classes.")

    # 3. Validate target percentage
    if isinstance(target_percentage, bool) or not isinstance(target_percentage, (int, float)):
        raise TypeError("Target percentage must be a number.")
    if target_percentage <= 0 or target_percentage > 100:
        raise ValueError("Target percentage must be greater than 0 and at most 100.")

    return clean_name


# =====================================================================
# Database Operations
# =====================================================================

def init_db(db_path: str) -> None:
    """
    Initializes the database schema if it doesn't already exist.

    Table schema:
    - id: Auto-incrementing unique integer primary key.
    - name: Text, unique across the table (case-insensitive via COLLATE NOCASE).
    - attended_classes: Non-negative integer.
    - total_classes: Non-negative integer >= attended_classes.
    - target_percentage: Real number strictly between 0 and 100.
    """
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS subjects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE COLLATE NOCASE,
        attended_classes INTEGER NOT NULL DEFAULT 0,
        total_classes INTEGER NOT NULL DEFAULT 0,
        target_percentage REAL NOT NULL DEFAULT 75.0,
        CHECK (attended_classes >= 0),
        CHECK (total_classes >= 0),
        CHECK (attended_classes <= total_classes),
        CHECK (target_percentage > 0.0 AND target_percentage <= 100.0)
    );
    """
    with get_connection(db_path) as conn:
        conn.execute(create_table_sql)


def add_subject(
    db_path: str,
    name: str,
    attended_classes: int = 0,
    total_classes: int = 0,
    target_percentage: float = 75.0
) -> int:
    """
    Validates and inserts a new subject into the database.

    Returns:
        int: The primary key (id) of the newly created subject row.

    Raises:
        ValueError / TypeError: For invalid input values or types.
        DuplicateSubjectError: If a subject with the same name already exists.
    """
    clean_name = _validate_subject_inputs(
        name, attended_classes, total_classes, target_percentage
    )

    insert_sql = """
    INSERT INTO subjects (name, attended_classes, total_classes, target_percentage)
    VALUES (?, ?, ?, ?);
    """
    try:
        with get_connection(db_path) as conn:
            cursor = conn.execute(
                insert_sql,
                (clean_name, attended_classes, total_classes, float(target_percentage))
            )
            return cursor.lastrowid
    except sqlite3.IntegrityError as err:
        # SQLite raises IntegrityError on UNIQUE constraint violations
        if "UNIQUE" in str(err).upper():
            raise DuplicateSubjectError(
                f"A subject with the name '{clean_name}' already exists."
            ) from None
        raise AttendWiseDBError("Failed to add subject due to a database constraint.") from None


def get_all_subjects(db_path: str) -> List[Dict[str, Any]]:
    """
    Retrieves all subjects ordered alphabetically by name.

    Returns:
        List[Dict[str, Any]]: List of dictionary representations of each subject.
    """
    query_sql = """
    SELECT id, name, attended_classes, total_classes, target_percentage
    FROM subjects
    ORDER BY name COLLATE NOCASE ASC;
    """
    with get_connection(db_path) as conn:
        cursor = conn.execute(query_sql)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def get_subject_by_id(db_path: str, subject_id: int) -> Optional[Dict[str, Any]]:
    """
    Retrieves a single subject by its ID.

    Returns:
        dict: The subject record if found.
        None: If no subject with the specified ID exists.
    """
    if isinstance(subject_id, bool) or not isinstance(subject_id, int):
        raise TypeError("Subject ID must be an integer.")

    query_sql = """
    SELECT id, name, attended_classes, total_classes, target_percentage
    FROM subjects
    WHERE id = ?;
    """
    with get_connection(db_path) as conn:
        cursor = conn.execute(query_sql, (subject_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def update_subject(
    db_path: str,
    subject_id: int,
    name: str,
    attended_classes: int,
    total_classes: int,
    target_percentage: float
) -> None:
    """
    Updates all fields of an existing subject.

    Raises:
        SubjectNotFoundError: If the subject_id does not exist.
        DuplicateSubjectError: If renaming conflicts with another existing subject.
        ValueError / TypeError: For invalid input data.
    """
    if isinstance(subject_id, bool) or not isinstance(subject_id, int):
        raise TypeError("Subject ID must be an integer.")

    clean_name = _validate_subject_inputs(
        name, attended_classes, total_classes, target_percentage
    )

    update_sql = """
    UPDATE subjects
    SET name = ?,
        attended_classes = ?,
        total_classes = ?,
        target_percentage = ?
    WHERE id = ?;
    """
    try:
        with get_connection(db_path) as conn:
            cursor = conn.execute(
                update_sql,
                (clean_name, attended_classes, total_classes, float(target_percentage), subject_id)
            )
            if cursor.rowcount == 0:
                raise SubjectNotFoundError(f"Subject with ID {subject_id} was not found.")
    except sqlite3.IntegrityError as err:
        if "UNIQUE" in str(err).upper():
            raise DuplicateSubjectError(
                f"Cannot rename to '{clean_name}' because that name is already in use."
            ) from None
        raise AttendWiseDBError("Failed to update subject due to a database constraint.") from None


def record_class_status(
    db_path: str,
    subject_id: int,
    attended_class: bool
) -> Dict[str, Any]:
    """
    Records the outcome of one additional class for a subject.

    - If attended_class is True: Increments both attended_classes and total_classes by 1.
    - If attended_class is False: Increments only total_classes by 1.

    Returns:
        Dict[str, Any]: The updated subject record.

    Raises:
        SubjectNotFoundError: If the subject_id does not exist.
        TypeError: If attended_class is not a boolean.
    """
    if isinstance(subject_id, bool) or not isinstance(subject_id, int):
        raise TypeError("Subject ID must be an integer.")
    if not isinstance(attended_class, bool):
        raise TypeError("attended_class parameter must be a boolean (True or False).")

    if attended_class:
        update_sql = """
        UPDATE subjects
        SET attended_classes = attended_classes + 1,
            total_classes = total_classes + 1
        WHERE id = ?;
        """
    else:
        update_sql = """
        UPDATE subjects
        SET total_classes = total_classes + 1
        WHERE id = ?;
        """

    with get_connection(db_path) as conn:
        cursor = conn.execute(update_sql, (subject_id,))
        if cursor.rowcount == 0:
            raise SubjectNotFoundError(f"Subject with ID {subject_id} was not found.")

        # Fetch and return the newly updated state
        fetch_cursor = conn.execute(
            "SELECT id, name, attended_classes, total_classes, target_percentage FROM subjects WHERE id = ?;",
            (subject_id,)
        )
        updated_row = fetch_cursor.fetchone()
        return dict(updated_row)


def delete_subject(db_path: str, subject_id: int) -> None:
    """
    Deletes a subject from the database by its ID.

    Raises:
        SubjectNotFoundError: If no subject with the specified ID exists.
    """
    if isinstance(subject_id, bool) or not isinstance(subject_id, int):
        raise TypeError("Subject ID must be an integer.")

    delete_sql = "DELETE FROM subjects WHERE id = ?;"
    with get_connection(db_path) as conn:
        cursor = conn.execute(delete_sql, (subject_id,))
        if cursor.rowcount == 0:
            raise SubjectNotFoundError(f"Subject with ID {subject_id} was not found.")
