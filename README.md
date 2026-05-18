# PyReps

A spaced-repetition Python coding flashcard system for coding pattern practice, built with PyQt6.

---

## Setup

### 1. Clone & install dependencies

```bash
git clone <repo>
cd py-reps
pip install -r requirements.txt
```

### 2. Initialise your PyReps root directory

By default the app looks for `~/pyreps/`. You can change this via  
**Settings → Configure Root Directory…** inside the app.

The root directory must follow this structure:

```
pyreps/
├── questions/
│   ├── 001_remove_punctuation/
│   │   ├── question.md       # Problem statement (Markdown)
│   │   ├── template.py       # Function signature + docstring (body = pass)
│   │   └── test_cases.py     # pytest tests that import from solution
│   ├── 002_counter_most_common/
│   │   └── ...
│   └── 003_flatten_nested_list/
│       └── ...
├── working/                  # Auto-managed by the app — do NOT commit
│   ├── solution.py
│   └── test_cases.py
└── results/
    └── progress.json         # Spaced-repetition state
```

This repository ships the sample questions inside `pyreps/questions/`.  
Copy the whole `pyreps/` folder to your home directory (or point the app at it):

```bash
cp -r pyreps ~/pyreps
```

### 3. Run the app

```bash
python app.py
```

---

## Usage

| Action | How |
|---|---|
| Submit solution | Click **Submit** or press `Ctrl+Enter` |
| Next card | Click **Next Card** or press `Ctrl+Right` |
| Skip card | Click **Skip** (marks as incorrect) |
| Reload session | `Ctrl+R` or **File → Reload Session** |
| Change root dir | **Settings → Configure Root Directory…** |

---

## Spaced Repetition Algorithm

| Event | Effect |
|---|---|
| Correct answer | `interval_days × 2` (max 30), `next_review = today + interval` |
| Incorrect / Skip | `interval_days = 1`, `next_review = tomorrow` |
| New card | `next_review = today` (appears immediately) |

Progress is persisted in `results/progress.json`.

---

## Adding New Questions

1. Create a new numbered folder under `questions/`, e.g. `004_my_question/`.
2. Add `question.md`, `template.py`, and `test_cases.py`.
3. In `test_cases.py`, import from `solution` (not `template`) — the app copies `template.py` → `solution.py` in `working/` when the card is loaded.
4. Reload the app — the new card will appear on its first due date (today).

---

## Requirements

- Python 3.10+
- PyQt6
- pytest
- markdown2
