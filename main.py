"""
main.py - AttendWise Mobile Interface

A clean, modern mobile attendance calculator application built with Python and Flet.
Integrates with:
- calculator.py: Core attendance and target calculation formulas.
- database.py: SQLite persistent storage and atomic class updates.

Design:
- Mobile-first layout (width restricted and centered on larger desktop displays).
- Deep Navy header and summary cards (#0F172A, #1E293B).
- Off-white background (#F8FAFC) with Mint Green (#10B981) and Red (#EF4444) accents.
- Color + text labels on all badges for accessibility.
- Confirmation dialogs before destructive actions.
- Double-tap debounce protection to prevent duplicate attendance increments.
"""

import os
import math
from pathlib import Path
from typing import List, Dict, Any, Optional

import flet as ft

# Existing backend modules (Source of Truth)
from calculator import (
    calculate_percentage,
    classes_needed_to_reach_target,
    classes_can_miss,
)
from database import (
    init_db,
    add_subject,
    get_all_subjects,
    update_subject,
    record_class_status,
    delete_subject,
    DuplicateSubjectError,
    SubjectNotFoundError,
)


# =====================================================================
# Database Path Resolution
# =====================================================================

def get_database_path() -> str:
    """
    Returns the persistent application database path.

    Resolution order:
    1. ATTENDWISE_DB_PATH environment variable (useful for testing or overrides).
    2. Local workspace directory 'attendwise.db' if writable.
    3. Platform-specific user data directory (%LOCALAPPDATA%/AttendWise on Windows).
    """
    env_override = os.environ.get("ATTENDWISE_DB_PATH")
    if env_override:
        return env_override

    # Use current working directory by default for beginner transparency and easy inspection
    local_db = Path("attendwise.db")
    try:
        # Check if current directory is writable
        local_db.touch(exist_ok=True)
        return str(local_db.resolve())
    except Exception:
        # Fallback to user AppData
        if os.name == "nt":
            base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or str(Path.home())
            data_dir = Path(base) / "AttendWise"
        else:
            data_dir = Path.home() / ".attendwise"

        data_dir.mkdir(parents=True, exist_ok=True)
        return str((data_dir / "attendwise.db").resolve())


# =====================================================================
# Color Palette & Design Tokens
# =====================================================================

NAVY_DARK = "#0F172A"       # Header background
NAVY_SURFACE = "#1E293B"    # Card headers / primary buttons
BG_LIGHT = "#F8FAFC"        # Page background
CARD_BG = "#FFFFFF"         # Subject card background
TEXT_MAIN = "#0F172A"       # Primary text
TEXT_MUTED = "#64748B"      # Subtitles and labels
MINT_GREEN = "#10B981"      # Safe / Target reached accent
CORAL_RED = "#EF4444"       # Deficit / Danger accent
AMBER_WARN = "#F59E0B"      # Attention accent
BORDER_COLOR = "#E2E8F0"    # Subtle borders


# =====================================================================
# Main Application Class
# =====================================================================

class AttendWiseApp:
    def __init__(self, page: ft.Page, db_path: Optional[str] = None):
        self.page = page
        self.db_path = db_path or get_database_path()

        # Initialize SQLite database
        init_db(self.db_path)

        # Debounce lock to prevent rapid double-clicks from recording twice
        self.is_busy = False

        # Configure page properties for a mobile-first experience
        self.page.title = "AttendWise"
        self.page.bgcolor = BG_LIGHT
        self.page.theme_mode = ft.ThemeMode.LIGHT
        self.page.padding = 0

        # UI Containers
        self.summary_container = ft.Container()
        self.cards_column = ft.Column(spacing=14, scroll=ft.ScrollMode.ADAPTIVE)

        # Build initial UI and load data
        self.build_ui()
        self.load_data()

    def build_ui(self):
        """Assembles the primary page layout."""
        # Top App Bar
        app_bar = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.SCHOOL_ROUNDED, color=ft.Colors.WHITE, size=28),
                    ft.Text(
                        "AttendWise",
                        size=22,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.WHITE,
                    ),
                    ft.Container(expand=True),
                    ft.IconButton(
                        icon=ft.Icons.REFRESH_ROUNDED,
                        icon_color=ft.Colors.WHITE,
                        tooltip="Refresh Attendance",
                        on_click=lambda e: self.load_data(show_toast=True),
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            bgcolor=NAVY_DARK,
            padding=ft.Padding.only(left=20, right=16, top=16, bottom=16),
        )

        # Floating Action Button for adding a new subject
        self.page.floating_action_button = ft.FloatingActionButton(
            bgcolor=NAVY_SURFACE,
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.ADD_ROUNDED, color=ft.Colors.WHITE),
                    ft.Text("Add Subject", color=ft.Colors.WHITE, weight=ft.FontWeight.W_600),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                tight=True,
            ),
            on_click=lambda e: self.show_add_subject_dialog(),
        )

        # Center content on desktop to simulate a clean mobile phone screen (max 480px width)
        content_column = ft.Column(
            controls=[
                self.summary_container,
                ft.Container(
                    content=ft.Text(
                        "YOUR SUBJECTS",
                        size=12,
                        weight=ft.FontWeight.BOLD,
                        color=TEXT_MUTED,
                    ),
                    padding=ft.Padding.only(left=4, top=10, bottom=4),
                ),
                self.cards_column,
                ft.Container(height=70),  # Bottom padding so FAB doesn't obscure the last card
            ],
            spacing=8,
        )

        mobile_frame = ft.Container(
            content=content_column,
            width=480,
            padding=ft.Padding.symmetric(horizontal=16, vertical=12),
        )

        # Outer wrapper centering the frame
        centered_layout = ft.Container(
            content=ft.Column(
                controls=[
                    app_bar,
                    ft.Row(
                        controls=[mobile_frame],
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                ],
                scroll=ft.ScrollMode.ADAPTIVE,
                spacing=0,
                expand=True,
            ),
            expand=True,
        )

        self.page.add(centered_layout)

    def load_data(self, show_toast: bool = False):
        """
        Fetches all subjects from the database, recomputes metrics,
        and refreshes the UI.
        """
        try:
            subjects = get_all_subjects(self.db_path)
        except Exception as e:
            self.show_message(f"Error loading subjects: {e}", is_error=True)
            return

        # 1. Update overall dashboard summary
        self.update_summary(subjects)

        # 2. Update subjects list
        self.cards_column.controls.clear()

        if not subjects:
            self.cards_column.controls.append(
                ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Icon(ft.Icons.AUTO_STORIES_OUTLINED, size=56, color=TEXT_MUTED),
                            ft.Text(
                                "No subjects added yet!",
                                size=18,
                                weight=ft.FontWeight.BOLD,
                                color=TEXT_MAIN,
                            ),
                            ft.Text(
                                "Tap '+ Add Subject' below to start tracking your attendance.",
                                size=14,
                                color=TEXT_MUTED,
                                text_align=ft.TextAlign.CENTER,
                            ),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=10,
                    ),
                    padding=ft.Padding.symmetric(vertical=48, horizontal=24),
                    alignment=ft.Alignment.CENTER,
                )
            )
        else:
            for subject in subjects:
                card = self.create_subject_card(subject)
                self.cards_column.controls.append(card)

        self.page.update()

        if show_toast:
            self.show_message("Attendance refreshed!")

    def update_summary(self, subjects: List[Dict[str, Any]]):
        """
        Computes and renders the top overall attendance summary card.
        Uses sum(attended) / sum(total) - NOT an average of percentages!
        """
        total_subjects = len(subjects)
        sum_attended = sum(s["attended_classes"] for s in subjects)
        sum_conducted = sum(s["total_classes"] for s in subjects)

        # Calculate overall attendance percentage
        overall_pct = calculate_percentage(sum_attended, sum_conducted)

        # Count subjects below target
        below_target_count = 0
        for s in subjects:
            s_pct = calculate_percentage(s["attended_classes"], s["total_classes"])
            # If classes have been held and percentage is below target
            if s_pct is not None and s_pct < s["target_percentage"]:
                below_target_count += 1

        # Determine overall text and color
        if overall_pct is None:
            pct_display = "No attendance recorded"
            pct_color = ft.Colors.WHITE
            overall_sub = "Add classes to see overall stats"
        else:
            pct_display = f"{overall_pct:.1f}%"
            pct_color = MINT_GREEN if overall_pct >= 75.0 else CORAL_RED
            overall_sub = f"{sum_attended} of {sum_conducted} total classes attended"

        summary_card = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Text("OVERALL ATTENDANCE", size=12, weight=ft.FontWeight.W_600, color="#94A3B8"),
                            ft.Icon(ft.Icons.DONUT_LARGE_ROUNDED, size=18, color="#94A3B8"),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Text(
                        pct_display,
                        size=34,
                        weight=ft.FontWeight.BOLD,
                        color=pct_color,
                    ),
                    ft.Text(overall_sub, size=13, color="#CBD5E1"),
                    ft.Divider(color="#334155", height=20),
                    ft.Row(
                        controls=[
                            # Metric 1: Subjects Count
                            ft.Column(
                                controls=[
                                    ft.Text("Tracking", size=11, color="#94A3B8"),
                                    ft.Text(f"{total_subjects} Subjects", size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                                ],
                                spacing=2,
                            ),
                            # Metric 2: Below Target Alert
                            ft.Container(
                                content=ft.Row(
                                    controls=[
                                        ft.Icon(
                                            ft.Icons.WARNING_AMBER_ROUNDED if below_target_count > 0 else ft.Icons.CHECK_CIRCLE_ROUNDED,
                                            size=16,
                                            color=CORAL_RED if below_target_count > 0 else MINT_GREEN,
                                        ),
                                        ft.Text(
                                            f"{below_target_count} Below Target" if below_target_count > 0 else "All On Track",
                                            size=13,
                                            weight=ft.FontWeight.W_600,
                                            color=CORAL_RED if below_target_count > 0 else MINT_GREEN,
                                        ),
                                    ],
                                    spacing=4,
                                ),
                                bgcolor="#0F172A",
                                padding=ft.Padding.symmetric(horizontal=10, vertical=6),
                                border_radius=8,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                ],
                spacing=4,
            ),
            bgcolor=NAVY_SURFACE,
            border_radius=16,
            padding=ft.Padding.all(18),
            shadow=ft.BoxShadow(blur_radius=12, color="#1E293B33"),
        )

        self.summary_container.content = summary_card

    def create_subject_card(self, subject: Dict[str, Any]) -> ft.Container:
        """
        Creates a subject card displaying attendance stats, target progress,
        guidance messages, and quick action buttons.
        """
        sub_id = subject["id"]
        name = subject["name"]
        attended = subject["attended_classes"]
        total = subject["total_classes"]
        target = subject["target_percentage"]

        # Call calculator logic (Source of truth)
        pct = calculate_percentage(attended, total)
        needed = classes_needed_to_reach_target(attended, total, target)
        missable = classes_can_miss(attended, total, target)

        # 1. Determine Status and Guidance
        if pct is None:
            status_text = "No Classes Yet"
            status_color = TEXT_MUTED
            status_bg = "#E2E8F0"
            progress_val = 0.0
            guidance_icon = ft.Icons.INFO_OUTLINE_ROUNDED
            guidance_color = TEXT_MUTED
            guidance_bg = "#F1F5F9"
            guidance_msg = "No classes recorded yet. Ready for your first lecture!"
        elif pct >= target:
            status_text = f"On Track ({pct:.1f}%)"
            status_color = MINT_GREEN
            status_bg = "#ECFDF5"
            progress_val = min(1.0, pct / 100.0)
            guidance_icon = ft.Icons.CHECK_CIRCLE_OUTLINE_ROUNDED
            guidance_color = MINT_GREEN
            guidance_bg = "#ECFDF5"
            if missable > 0:
                guidance_msg = f"You can safely miss up to {missable} class{'es' if missable != 1 else ''}."
            else:
                guidance_msg = "You are exactly at target! Do not miss the next class."
        else:
            status_text = f"Below Target ({pct:.1f}%)"
            status_color = CORAL_RED
            status_bg = "#FEF2F2"
            progress_val = min(1.0, pct / 100.0)
            guidance_icon = ft.Icons.ERROR_OUTLINE_ROUNDED
            guidance_color = CORAL_RED
            guidance_bg = "#FEF2F2"
            if math.isinf(needed):
                guidance_msg = "100% target cannot be reached after an absence."
            else:
                guidance_msg = f"Attend next {needed} consecutive class{'es' if needed != 1 else ''} to reach {target:.0f}%."

        # Card Layout
        card_content = ft.Column(
            controls=[
                # Row 1: Title and Options Menu (Edit/Delete)
                ft.Row(
                    controls=[
                        ft.Text(
                            name,
                            size=18,
                            weight=ft.FontWeight.BOLD,
                            color=TEXT_MAIN,
                            expand=True,
                        ),
                        # Status Badge
                        ft.Container(
                            content=ft.Text(
                                status_text,
                                size=11,
                                weight=ft.FontWeight.BOLD,
                                color=status_color,
                            ),
                            bgcolor=status_bg,
                            padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                            border_radius=8,
                        ),
                        # Action Menu
                        ft.PopupMenuButton(
                            items=[
                                ft.PopupMenuItem(
                                    icon=ft.Icons.EDIT_ROUNDED,
                                    content="Edit Subject",
                                    on_click=lambda e, s=subject: self.show_edit_subject_dialog(s),
                                ),
                                ft.PopupMenuItem(
                                    icon=ft.Icons.DELETE_ROUNDED,
                                    content="Delete Subject",
                                    on_click=lambda e, s=subject: self.show_delete_confirmation(s),
                                ),
                            ],
                            icon=ft.Icons.MORE_VERT_ROUNDED,
                            icon_color=TEXT_MUTED,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),

                # Row 2: Attendance numbers and progress bar
                ft.Row(
                    controls=[
                        ft.Text(
                            f"{attended} / {total} classes attended",
                            size=13,
                            color=TEXT_MUTED,
                        ),
                        ft.Text(
                            f"Goal: {target:.0f}%",
                            size=13,
                            weight=ft.FontWeight.W_500,
                            color=TEXT_MUTED,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.ProgressBar(
                    value=progress_val,
                    color=status_color,
                    bgcolor="#E2E8F0",
                    height=8,
                    border_radius=4,
                ),

                # Row 3: Guidance Banner
                ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.Icon(guidance_icon, size=16, color=guidance_color),
                            ft.Text(
                                guidance_msg,
                                size=12,
                                weight=ft.FontWeight.W_500,
                                color=TEXT_MAIN,
                                expand=True,
                            ),
                        ],
                        spacing=8,
                    ),
                    bgcolor=guidance_bg,
                    padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                    border_radius=8,
                ),

                # Row 4: Quick Action Buttons (+ Attended / + Missed)
                ft.Row(
                    controls=[
                        ft.FilledButton(
                            content=ft.Row(
                                [
                                    ft.Icon(ft.Icons.CHECK_ROUNDED, size=16, color=ft.Colors.WHITE),
                                    ft.Text("+ Attended", color=ft.Colors.WHITE, weight=ft.FontWeight.W_600),
                                ],
                                alignment=ft.MainAxisAlignment.CENTER,
                                spacing=4,
                            ),
                            bgcolor=MINT_GREEN,
                            style=ft.ButtonStyle(
                                shape=ft.RoundedRectangleBorder(radius=8),
                                padding=ft.Padding.symmetric(horizontal=14, vertical=10),
                            ),
                            expand=True,
                            on_click=lambda e, sid=sub_id, sname=name: self.handle_quick_attendance(sid, sname, True),
                        ),
                        ft.OutlinedButton(
                            content=ft.Row(
                                [
                                    ft.Icon(ft.Icons.CLOSE_ROUNDED, size=16, color=CORAL_RED),
                                    ft.Text("+ Missed", color=CORAL_RED, weight=ft.FontWeight.W_600),
                                ],
                                alignment=ft.MainAxisAlignment.CENTER,
                                spacing=4,
                            ),
                            style=ft.ButtonStyle(
                                shape=ft.RoundedRectangleBorder(radius=8),
                                side=ft.BorderSide(1.5, CORAL_RED),
                                padding=ft.Padding.symmetric(horizontal=14, vertical=10),
                            ),
                            expand=True,
                            on_click=lambda e, sid=sub_id, sname=name: self.handle_quick_attendance(sid, sname, False),
                        ),
                    ],
                    spacing=10,
                ),
            ],
            spacing=10,
        )

        return ft.Container(
            content=card_content,
            bgcolor=CARD_BG,
            border_radius=16,
            padding=ft.Padding.all(16),
            border=ft.Border.all(1, BORDER_COLOR),
            shadow=ft.BoxShadow(blur_radius=6, color="#00000008"),
        )

    # =====================================================================
    # Quick Attendance Action (Debounced)
    # =====================================================================

    def handle_quick_attendance(self, subject_id: int, subject_name: str, attended_class: bool):
        """
        Records 1 attended or missed class.
        Includes double-click debounce protection.
        """
        if self.is_busy:
            return

        self.is_busy = True
        try:
            record_class_status(self.db_path, subject_id, attended_class)
            action_desc = "attended" if attended_class else "missed"
            self.show_message(f"Recorded 1 {action_desc} class for {subject_name}!")
            self.load_data()
        except SubjectNotFoundError:
            self.show_message("Subject no longer exists.", is_error=True)
            self.load_data()
        except Exception as e:
            self.show_message(f"Failed to record attendance: {e}", is_error=True)
        finally:
            self.is_busy = False

    # =====================================================================
    # Add Subject Dialog
    # =====================================================================

    def show_add_subject_dialog(self):
        """Displays dialog for adding a new subject with validation."""
        name_input = ft.TextField(
            label="Subject Name",
            hint_text="e.g. Python Programming",
            autofocus=True,
            border_color=BORDER_COLOR,
        )
        attended_input = ft.TextField(
            label="Classes Attended",
            value="0",
            keyboard_type=ft.KeyboardType.NUMBER,
            border_color=BORDER_COLOR,
        )
        total_input = ft.TextField(
            label="Total Classes Conducted",
            value="0",
            keyboard_type=ft.KeyboardType.NUMBER,
            border_color=BORDER_COLOR,
        )
        target_input = ft.TextField(
            label="Target Attendance %",
            value="75",
            keyboard_type=ft.KeyboardType.NUMBER,
            border_color=BORDER_COLOR,
        )
        error_label = ft.Text("", color=CORAL_RED, size=12, visible=False)

        def save_new_subject(e):
            # 1. Parse and validate inputs
            raw_name = name_input.value or ""
            clean_name = raw_name.strip()

            if not clean_name:
                error_label.value = "Subject name cannot be empty."
                error_label.visible = True
                self.page.update()
                return

            try:
                attended = int(attended_input.value or 0)
                total = int(total_input.value or 0)
            except ValueError:
                error_label.value = "Class counts must be whole numbers."
                error_label.visible = True
                self.page.update()
                return

            try:
                target = float(target_input.value or 75.0)
            except ValueError:
                error_label.value = "Target percentage must be a valid number."
                error_label.visible = True
                self.page.update()
                return

            if attended < 0 or total < 0:
                error_label.value = "Class counts cannot be negative."
                error_label.visible = True
                self.page.update()
                return

            if attended > total:
                error_label.value = "Attended classes cannot exceed total classes."
                error_label.visible = True
                self.page.update()
                return

            if target <= 0 or target > 100:
                error_label.value = "Target must be greater than 0% and at most 100%."
                error_label.visible = True
                self.page.update()
                return

            # 2. Save to database
            try:
                add_subject(self.db_path, clean_name, attended, total, target)
                self.page.pop_dialog()
                self.show_message(f"Added '{clean_name}' successfully!")
                self.load_data()
            except DuplicateSubjectError:
                error_label.value = f"A subject named '{clean_name}' already exists."
                error_label.visible = True
                self.page.update()
            except Exception as ex:
                error_label.value = f"Could not save subject: {ex}"
                error_label.visible = True
                self.page.update()

        dialog = ft.AlertDialog(
            title=ft.Text("Add New Subject", weight=ft.FontWeight.BOLD),
            content=ft.Container(
                content=ft.Column(
                    controls=[
                        name_input,
                        ft.Row([attended_input, total_input], spacing=10),
                        target_input,
                        error_label,
                    ],
                    spacing=12,
                    tight=True,
                ),
                width=360,
            ),
            actions=[
                ft.TextButton("Cancel", on_click=lambda e: self.page.pop_dialog()),
                ft.FilledButton(
                    "Save Subject",
                    bgcolor=NAVY_SURFACE,
                    color=ft.Colors.WHITE,
                    on_click=save_new_subject,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        self.page.show_dialog(dialog)

    # =====================================================================
    # Edit Subject Dialog
    # =====================================================================

    def show_edit_subject_dialog(self, subject: Dict[str, Any]):
        """Displays dialog for editing an existing subject."""
        sub_id = subject["id"]

        name_input = ft.TextField(
            label="Subject Name",
            value=subject["name"],
            border_color=BORDER_COLOR,
        )
        attended_input = ft.TextField(
            label="Classes Attended",
            value=str(subject["attended_classes"]),
            keyboard_type=ft.KeyboardType.NUMBER,
            border_color=BORDER_COLOR,
        )
        total_input = ft.TextField(
            label="Total Classes Conducted",
            value=str(subject["total_classes"]),
            keyboard_type=ft.KeyboardType.NUMBER,
            border_color=BORDER_COLOR,
        )
        target_input = ft.TextField(
            label="Target Attendance %",
            value=str(subject["target_percentage"]),
            keyboard_type=ft.KeyboardType.NUMBER,
            border_color=BORDER_COLOR,
        )
        error_label = ft.Text("", color=CORAL_RED, size=12, visible=False)

        def save_edited_subject(e):
            clean_name = (name_input.value or "").strip()
            if not clean_name:
                error_label.value = "Subject name cannot be empty."
                error_label.visible = True
                self.page.update()
                return

            try:
                attended = int(attended_input.value or 0)
                total = int(total_input.value or 0)
            except ValueError:
                error_label.value = "Class counts must be whole numbers."
                error_label.visible = True
                self.page.update()
                return

            try:
                target = float(target_input.value or 75.0)
            except ValueError:
                error_label.value = "Target percentage must be a number."
                error_label.visible = True
                self.page.update()
                return

            if attended < 0 or total < 0:
                error_label.value = "Class counts cannot be negative."
                error_label.visible = True
                self.page.update()
                return

            if attended > total:
                error_label.value = "Attended classes cannot exceed total classes."
                error_label.visible = True
                self.page.update()
                return

            if target <= 0 or target > 100:
                error_label.value = "Target must be between 0 and 100."
                error_label.visible = True
                self.page.update()
                return

            try:
                update_subject(self.db_path, sub_id, clean_name, attended, total, target)
                self.page.pop_dialog()
                self.show_message(f"Updated '{clean_name}' successfully!")
                self.load_data()
            except DuplicateSubjectError:
                error_label.value = f"Another subject named '{clean_name}' already exists."
                error_label.visible = True
                self.page.update()
            except SubjectNotFoundError:
                self.page.pop_dialog()
                self.show_message("Subject was not found.", is_error=True)
                self.load_data()
            except Exception as ex:
                error_label.value = f"Failed to update: {ex}"
                error_label.visible = True
                self.page.update()

        dialog = ft.AlertDialog(
            title=ft.Text("Edit Subject", weight=ft.FontWeight.BOLD),
            content=ft.Container(
                content=ft.Column(
                    controls=[
                        name_input,
                        ft.Row([attended_input, total_input], spacing=10),
                        target_input,
                        error_label,
                    ],
                    spacing=12,
                    tight=True,
                ),
                width=360,
            ),
            actions=[
                ft.TextButton("Cancel", on_click=lambda e: self.page.pop_dialog()),
                ft.FilledButton(
                    "Save Changes",
                    bgcolor=NAVY_SURFACE,
                    color=ft.Colors.WHITE,
                    on_click=save_edited_subject,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        self.page.show_dialog(dialog)

    # =====================================================================
    # Delete Confirmation Dialog
    # =====================================================================

    def show_delete_confirmation(self, subject: Dict[str, Any]):
        """Prompts the user before permanently deleting a subject."""
        sub_id = subject["id"]
        name = subject["name"]

        def perform_delete(e):
            try:
                delete_subject(self.db_path, sub_id)
                self.page.pop_dialog()
                self.show_message(f"Deleted '{name}'.")
                self.load_data()
            except Exception as ex:
                self.page.pop_dialog()
                self.show_message(f"Failed to delete subject: {ex}", is_error=True)

        dialog = ft.AlertDialog(
            title=ft.Text("Delete Subject?", weight=ft.FontWeight.BOLD),
            content=ft.Text(f"Are you sure you want to delete '{name}'? All recorded attendance for this subject will be removed."),
            actions=[
                ft.TextButton("Cancel", on_click=lambda e: self.page.pop_dialog()),
                ft.FilledButton(
                    "Delete",
                    bgcolor=CORAL_RED,
                    color=ft.Colors.WHITE,
                    on_click=perform_delete,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        self.page.show_dialog(dialog)

    # =====================================================================
    # User Notification (SnackBar)
    # =====================================================================

    def show_message(self, message: str, is_error: bool = False):
        """Displays a clean bottom notification toast."""
        snack = ft.SnackBar(
            content=ft.Text(message, color=ft.Colors.WHITE, weight=ft.FontWeight.W_500),
            bgcolor=CORAL_RED if is_error else NAVY_SURFACE,
            duration=3000,
        )
        self.page.show_dialog(snack)


# =====================================================================
# Application Entry Point
# =====================================================================

def main(page: ft.Page):
    AttendWiseApp(page)


if __name__ == "__main__":
    ft.run(main)