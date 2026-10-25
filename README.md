# AttendWise

AttendWise is a desktop attendance tracker built with Python and Flet. Track
attendance for multiple subjects, set a target percentage for each, and see
whether you are on track.

## Requirements

- Python 3.12
- VS Code with the Python extension (optional, for the included Run AttendWise
  launch profile)

## Run the app

1. Create and activate a virtual environment:

   ```powershell
   py -3.12 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

2. Install the app dependency:

   ```powershell
   python -m pip install -r requirements.txt
   ```

3. Start AttendWise:

   ```powershell
   python main.py
   ```

In VS Code, you can also select the virtual environment as the Python
interpreter and press **F5** to run the **Run AttendWise** launch profile.

## Use the app

- Select **Add Subject** to enter a subject, its current attendance counts, and
  an attendance target. The default target is 75%.
- Select **+ Attended** or **+ Missed** after each class to update the counts.
- Use a subject's three-dot menu to edit or delete it.
- The dashboard shows each subject's attendance percentage and guidance, plus
  an overall percentage calculated from all attended classes and all classes
  held.

The app creates `attendwise.db` in its working directory to store data. That
local database is intentionally excluded from Git; each user's attendance
records remain on their own machine.

## Run tests

Install pytest if it is not already available, then run:

```powershell
python -m pytest -q
```
