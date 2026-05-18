"""
PyReps — Python coding flashcard system for interview prep practice.
Entry point: app.py
"""

import sys
import os
import json
import shutil
import subprocess
import re
from datetime import date, timedelta
from pathlib import Path

import markdown2
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QSplitter, QTextBrowser, QPlainTextEdit, QLabel, QPushButton,
    QScrollArea, QFrame, QDialog, QLineEdit, QDialogButtonBox,
    QFileDialog, QMenuBar, QMessageBox, QStatusBar,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt6.QtGui import (
    QFont, QTextCharFormat, QColor, QSyntaxHighlighter,
    QTextDocument, QKeySequence, QShortcut, QAction, QPalette,
)


# ─────────────────────────────────────────────────────────────────────────────
# Config helpers
# ─────────────────────────────────────────────────────────────────────────────

CONFIG_FILE = Path.home() / ".pyreps_config.json"
DEFAULT_ROOT = Path(__file__).parent / "pyreps"


def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"root_dir": str(DEFAULT_ROOT)}


def save_config(cfg: dict):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)


# ─────────────────────────────────────────────────────────────────────────────
# Spaced repetition
# ─────────────────────────────────────────────────────────────────────────────

class SpacedRepetitionManager:
    def __init__(self, progress_path: Path):
        self.path = progress_path
        self.data: dict = {}
        self._load()

    def _load(self):
        if self.path.exists():
            try:
                with open(self.path) as f:
                    self.data = json.load(f)
            except Exception:
                self.data = {}
        else:
            self.data = {}

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w") as f:
            json.dump(self.data, f, indent=2)

    def _default_entry(self) -> dict:
        return {
            "times_correct": 0,
            "times_incorrect": 0,
            "last_reviewed": None,
            "next_review": str(date.today()),
            "interval_days": 1,
        }

    def get_entry(self, question_id: str) -> dict:
        if question_id not in self.data:
            self.data[question_id] = self._default_entry()
        return self.data[question_id]

    def is_due(self, question_id: str) -> bool:
        entry = self.get_entry(question_id)
        next_review = date.fromisoformat(entry["next_review"])
        return next_review <= date.today()

    def record_result(self, question_id: str, correct: bool):
        entry = self.get_entry(question_id)
        today = date.today()
        entry["last_reviewed"] = str(today)
        if correct:
            entry["times_correct"] += 1
            new_interval = min(entry["interval_days"] * 2, 30)
            entry["interval_days"] = new_interval
            entry["next_review"] = str(today + timedelta(days=new_interval))
        else:
            entry["times_incorrect"] += 1
            entry["interval_days"] = 1
            entry["next_review"] = str(today + timedelta(days=1))
        self.data[question_id] = entry
        self._save()

    def next_due_date(self) -> str:
        """Return the earliest next_review date across all cards."""
        dates = [
            date.fromisoformat(v["next_review"])
            for v in self.data.values()
            if v.get("next_review")
        ]
        if dates:
            return str(min(dates))
        return str(date.today())


# ─────────────────────────────────────────────────────────────────────────────
# Test runner (runs in a thread)
# ─────────────────────────────────────────────────────────────────────────────

class TestRunnerThread(QThread):
    finished = pyqtSignal(list, str)  # list of result dicts, raw output

    def __init__(self, working_dir: Path):
        super().__init__()
        self.working_dir = working_dir

    def run(self):
        test_file = self.working_dir / "test_cases.py"
        if not test_file.exists():
            self.finished.emit([], "test_cases.py not found in working dir.")
            return
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", str(test_file), "-v", "--tb=short", "--no-header"],
                capture_output=True,
                text=True,
                cwd=str(self.working_dir),
                timeout=30,
            )
            raw = result.stdout + result.stderr
            parsed = self._parse_pytest_output(raw)
            self.finished.emit(parsed, raw)
        except subprocess.TimeoutExpired:
            self.finished.emit([], "Tests timed out after 30 seconds.")
        except Exception as e:
            self.finished.emit([], f"Error running tests: {e}")

    def _parse_pytest_output(self, output: str) -> list:
        results = []
        for line in output.splitlines():
            passed = re.match(r"(.+)\s+PASSED", line)
            failed = re.match(r"(.+)\s+FAILED", line)
            error = re.match(r"(.+)\s+ERROR", line)
            if passed:
                results.append({"name": passed.group(1).strip(), "status": "PASSED", "detail": ""})
            elif failed:
                results.append({"name": failed.group(1).strip(), "status": "FAILED", "detail": ""})
            elif error:
                results.append({"name": error.group(1).strip(), "status": "ERROR", "detail": ""})

        # Attach failure details
        current_fail = None
        detail_lines = []
        in_fail = False
        for line in output.splitlines():
            if re.match(r"_{3,}", line) and "FAILURES" in line:
                in_fail = True
                continue
            if in_fail:
                short_match = re.match(r"_{3,} (.+) _{3,}", line)
                if short_match:
                    if current_fail is not None:
                        _attach_detail(results, current_fail, "\n".join(detail_lines))
                    current_fail = short_match.group(1).strip()
                    detail_lines = []
                else:
                    detail_lines.append(line)
        if current_fail is not None:
            _attach_detail(results, current_fail, "\n".join(detail_lines))

        return results


def _attach_detail(results: list, fail_name: str, detail: str):
    for r in results:
        if fail_name in r["name"] and r["status"] == "FAILED":
            r["detail"] = detail.strip()
            return


# ─────────────────────────────────────────────────────────────────────────────
# Python syntax highlighter
# ─────────────────────────────────────────────────────────────────────────────

class PythonHighlighter(QSyntaxHighlighter):
    def __init__(self, document: QTextDocument):
        super().__init__(document)
        self._rules = []

        keyword_fmt = QTextCharFormat()
        keyword_fmt.setForeground(QColor("#c792ea"))
        keyword_fmt.setFontWeight(700)
        keywords = [
            "False", "None", "True", "and", "as", "assert", "async", "await",
            "break", "class", "continue", "def", "del", "elif", "else",
            "except", "finally", "for", "from", "global", "if", "import",
            "in", "is", "lambda", "nonlocal", "not", "or", "pass", "raise",
            "return", "try", "while", "with", "yield",
        ]
        for kw in keywords:
            self._rules.append((re.compile(rf"\b{kw}\b"), keyword_fmt))

        builtin_fmt = QTextCharFormat()
        builtin_fmt.setForeground(QColor("#82aaff"))
        builtins = [
            "print", "len", "range", "enumerate", "zip", "map", "filter",
            "sorted", "reversed", "list", "dict", "set", "tuple", "str",
            "int", "float", "bool", "type", "isinstance", "hasattr",
            "getattr", "setattr", "open", "super", "object", "self",
        ]
        for b in builtins:
            self._rules.append((re.compile(rf"\b{b}\b"), builtin_fmt))

        str_fmt = QTextCharFormat()
        str_fmt.setForeground(QColor("#c3e88d"))
        self._rules.append((re.compile(r'"[^"\\]*(\\.[^"\\]*)*"'), str_fmt))
        self._rules.append((re.compile(r"'[^'\\]*(\\.[^'\\]*)*'"), str_fmt))

        comment_fmt = QTextCharFormat()
        comment_fmt.setForeground(QColor("#546e7a"))
        comment_fmt.setFontItalic(True)
        self._rules.append((re.compile(r"#[^\n]*"), comment_fmt))

        decorator_fmt = QTextCharFormat()
        decorator_fmt.setForeground(QColor("#ffcb6b"))
        self._rules.append((re.compile(r"@\w+"), decorator_fmt))

        number_fmt = QTextCharFormat()
        number_fmt.setForeground(QColor("#f78c6c"))
        self._rules.append((re.compile(r"\b\d+\.?\d*\b"), number_fmt))

    def highlightBlock(self, text: str):
        for pattern, fmt in self._rules:
            for match in pattern.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), fmt)


# ─────────────────────────────────────────────────────────────────────────────
# Settings dialog
# ─────────────────────────────────────────────────────────────────────────────

class SettingsDialog(QDialog):
    def __init__(self, current_root: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings — PyReps")
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)

        label = QLabel("PyReps root directory:")
        layout.addWidget(label)

        row = QHBoxLayout()
        self.path_edit = QLineEdit(current_root)
        row.addWidget(self.path_edit)
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse)
        row.addWidget(browse_btn)
        layout.addLayout(row)

        note = QLabel(
            "The root directory must contain a <b>questions/</b> subfolder "
            "and a <b>results/</b> subfolder."
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse(self):
        chosen = QFileDialog.getExistingDirectory(
            self, "Select PyReps root directory", self.path_edit.text()
        )
        if chosen:
            self.path_edit.setText(chosen)

    def get_path(self) -> str:
        return self.path_edit.text().strip()


# ─────────────────────────────────────────────────────────────────────────────
# Results panel
# ─────────────────────────────────────────────────────────────────────────────

class ResultsPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(300)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        header = QLabel("Test Results")
        header.setStyleSheet("font-weight: bold; font-size: 14px; color: #cdd3de;")
        layout.addWidget(header)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("border: none;")
        self.results_container = QWidget()
        self.results_layout = QVBoxLayout(self.results_container)
        self.results_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.results_container)
        layout.addWidget(self.scroll)

        self.summary_label = QLabel("")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

    def clear(self):
        while self.results_layout.count():
            child = self.results_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self.summary_label.setText("")

    def show_results(self, results: list, raw_output: str):
        self.clear()
        if not results:
            label = QLabel("No test results found.\n\nRaw output:\n" + raw_output[:500])
            label.setWordWrap(True)
            label.setStyleSheet("color: #f07178; font-size: 12px;")
            self.results_layout.addWidget(label)
            return

        passed = sum(1 for r in results if r["status"] == "PASSED")
        total = len(results)

        for r in results:
            frame = QFrame()
            frame.setFrameShape(QFrame.Shape.StyledPanel)
            fl = QVBoxLayout(frame)
            fl.setContentsMargins(6, 4, 6, 4)

            status = r["status"]
            icon = "✅" if status == "PASSED" else "❌"
            color = "#c3e88d" if status == "PASSED" else "#f07178"

            # Strip the file path prefix for display
            name = r["name"]
            if "::" in name:
                name = name.split("::")[-1]

            title = QLabel(f"{icon} {name}")
            title.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 12px;")
            title.setWordWrap(True)
            fl.addWidget(title)

            if r.get("detail"):
                detail = QLabel(r["detail"])
                detail.setStyleSheet("color: #89ddff; font-size: 11px; font-family: monospace;")
                detail.setWordWrap(True)
                fl.addWidget(detail)

            frame.setStyleSheet(
                f"QFrame {{ border: 1px solid {'#2d5a27' if status == 'PASSED' else '#5a2727'}; "
                f"border-radius: 4px; background: {'#1a2e1a' if status == 'PASSED' else '#2e1a1a'}; }}"
            )
            self.results_layout.addWidget(frame)

        color = "#c3e88d" if passed == total else "#f07178"
        self.summary_label.setStyleSheet(f"font-weight: bold; color: {color}; font-size: 13px;")
        self.summary_label.setText(f"{passed}/{total} tests passed")


# ─────────────────────────────────────────────────────────────────────────────
# Question panel
# ─────────────────────────────────────────────────────────────────────────────

class QuestionPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(300)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        self.name_label = QLabel("")
        self.name_label.setStyleSheet(
            "font-weight: bold; font-size: 14px; color: #cdd3de;"
        )
        self.name_label.setWordWrap(True)
        layout.addWidget(self.name_label)

        self.category_label = QLabel("")
        self.category_label.setStyleSheet(
            "font-size: 11px; color: #82aaff; font-style: italic; margin-bottom: 6px;"
        )
        layout.addWidget(self.category_label)

        self.text_browser = QTextBrowser()
        self.text_browser.setOpenExternalLinks(True)
        self.text_browser.setStyleSheet(
            "background: #1a1f2e; color: #cdd3de; border: none; font-size: 13px;"
        )
        layout.addWidget(self.text_browser)

    def load_question(self, question_id: str, md_path: Path):
        # Parse name and category from markdown
        self.name_label.setText(question_id.replace("_", " ").title())
        self.category_label.setText("")

        if not md_path.exists():
            self.text_browser.setHtml("<p style='color:#f07178'>question.md not found.</p>")
            return

        md_text = md_path.read_text()

        # Extract category tag if present
        cat_match = re.search(r"\*\*Category:\*\*\s*(.+)", md_text)
        if cat_match:
            self.category_label.setText(f"Category: {cat_match.group(1).strip()}")

        # Extract H1 as display name
        h1_match = re.match(r"#\s+(.+)", md_text)
        if h1_match:
            self.name_label.setText(h1_match.group(1).strip())

        html = markdown2.markdown(
            md_text,
            extras=["fenced-code-blocks", "tables", "strike", "code-friendly"],
        )
        styled = f"""
        <style>
            body {{ font-family: -apple-system, sans-serif; font-size: 13px; color: #cdd3de; }}
            h1, h2, h3 {{ color: #82aaff; }}
            code {{ background: #252d3d; color: #c3e88d; padding: 1px 4px;
                    border-radius: 3px; font-family: 'Courier New', monospace; }}
            pre {{ background: #252d3d; padding: 10px; border-radius: 4px;
                   overflow-x: auto; font-family: 'Courier New', monospace; }}
            strong {{ color: #ffcb6b; }}
            details {{ margin: 6px 0; }}
            summary {{ cursor: pointer; color: #89ddff; }}
        </style>
        {html}
        """
        self.text_browser.setHtml(styled)


# ─────────────────────────────────────────────────────────────────────────────
# Code editor
# ─────────────────────────────────────────────────────────────────────────────

class CodeEditor(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        font = QFont("Fira Code", 14)
        font.setStyleHint(QFont.StyleHint.Monospace)
        if not font.exactMatch():
            font = QFont("Courier New", 14)
            font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)
        self.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(" "))
        self.setStyleSheet(
            "background: #1a1f2e; color: #cdd3de; border: none; "
            "selection-background-color: #3d4f6e;"
        )
        self._highlighter = PythonHighlighter(self.document())

    def load_template(self, template_path: Path):
        if template_path.exists():
            self.setPlainText(template_path.read_text())
        else:
            self.setPlainText("# template.py not found\n")


# ─────────────────────────────────────────────────────────────────────────────
# Bottom bar
# ─────────────────────────────────────────────────────────────────────────────

class BottomBar(QWidget):
    submit_clicked = pyqtSignal()
    skip_clicked = pyqtSignal()
    next_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(52)
        self.setStyleSheet("background: #141824; border-top: 1px solid #2a3045;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(10)

        self.question_label = QLabel("No question loaded")
        self.question_label.setStyleSheet("color: #82aaff; font-size: 13px;")
        layout.addWidget(self.question_label)

        layout.addStretch()

        self.progress_label = QLabel("")
        self.progress_label.setStyleSheet("color: #546e7a; font-size: 12px;")
        layout.addWidget(self.progress_label)

        self.submit_btn = QPushButton("Submit")
        self.submit_btn.setShortcut(QKeySequence("Ctrl+Return"))
        self.submit_btn.setStyleSheet(_btn_style("#1565c0", "#1976d2", "#0d47a1"))
        self.submit_btn.setFixedHeight(32)
        self.submit_btn.clicked.connect(self.submit_clicked)
        layout.addWidget(self.submit_btn)

        self.skip_btn = QPushButton("Skip")
        self.skip_btn.setStyleSheet(_btn_style("#37474f", "#455a64", "#263238"))
        self.skip_btn.setFixedHeight(32)
        self.skip_btn.clicked.connect(self.skip_clicked)
        layout.addWidget(self.skip_btn)

        self.next_btn = QPushButton("Next Card  →")
        self.next_btn.setShortcut(QKeySequence("Ctrl+Right"))
        self.next_btn.setStyleSheet(_btn_style("#1b5e20", "#2e7d32", "#003300"))
        self.next_btn.setFixedHeight(32)
        self.next_btn.setVisible(False)
        self.next_btn.clicked.connect(self.next_clicked)
        layout.addWidget(self.next_btn)

    def set_question(self, name: str, index: int, total: int):
        self.question_label.setText(name)
        self.progress_label.setText(f"{index} of {total} due today")
        self.next_btn.setVisible(False)
        self.submit_btn.setEnabled(True)

    def show_next_button(self):
        self.next_btn.setVisible(True)
        self.submit_btn.setEnabled(False)


def _btn_style(bg: str, hover: str, pressed: str) -> str:
    return (
        f"QPushButton {{ background: {bg}; color: white; border: none; "
        f"border-radius: 4px; padding: 0 14px; font-size: 13px; }}"
        f"QPushButton:hover {{ background: {hover}; }}"
        f"QPushButton:pressed {{ background: {pressed}; }}"
        f"QPushButton:disabled {{ background: #2a2a2a; color: #555; }}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# No-cards-due overlay
# ─────────────────────────────────────────────────────────────────────────────

class NoDueCardsWidget(QWidget):
    def __init__(self, next_date: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon = QLabel("🎉")
        icon.setStyleSheet("font-size: 64px;")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon)

        msg = QLabel("All caught up!")
        msg.setStyleSheet("font-size: 28px; font-weight: bold; color: #c3e88d;")
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(msg)

        sub = QLabel(f"No cards are due today.\nNext review: {next_date}")
        sub.setStyleSheet("font-size: 16px; color: #82aaff; margin-top: 8px;")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(sub)


# ─────────────────────────────────────────────────────────────────────────────
# Main window
# ─────────────────────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PyReps — Interview Prep Flashcards")
        self.resize(1200, 750)

        self.config = load_config()
        self.root_dir = Path(self.config.get("root_dir", str(DEFAULT_ROOT)))

        self.due_questions: list[str] = []
        self.current_index: int = 0
        self.submitted: bool = False
        self._runner: TestRunnerThread | None = None

        self._setup_ui()
        self._setup_menu()
        self._load_session()

    # ── UI construction ───────────────────────────────────────────────────

    def _setup_ui(self):
        self.setStyleSheet("background: #1a1f2e; color: #cdd3de;")

        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Three-panel splitter
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(2)
        self.splitter.setStyleSheet(
            "QSplitter::handle { background: #2a3045; }"
        )

        self.question_panel = QuestionPanel()
        self.splitter.addWidget(self.question_panel)

        self.editor = CodeEditor()
        self.splitter.addWidget(self.editor)

        self.results_panel = ResultsPanel()
        self.splitter.addWidget(self.results_panel)

        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)

        root_layout.addWidget(self.splitter, 1)

        self.bottom_bar = BottomBar()
        self.bottom_bar.submit_clicked.connect(self._on_submit)
        self.bottom_bar.skip_clicked.connect(self._on_skip)
        self.bottom_bar.next_clicked.connect(self._on_next)
        root_layout.addWidget(self.bottom_bar)

        # Status bar
        self.status_bar = QStatusBar()
        self.status_bar.setStyleSheet(
            "background: #141824; color: #546e7a; font-size: 11px; border-top: none;"
        )
        self.setStatusBar(self.status_bar)

    def _setup_menu(self):
        mb = self.menuBar()
        mb.setStyleSheet(
            "QMenuBar { background: #141824; color: #cdd3de; }"
            "QMenuBar::item:selected { background: #1e2535; }"
            "QMenu { background: #1e2535; color: #cdd3de; }"
            "QMenu::item:selected { background: #2a3a5e; }"
        )

        # File menu
        file_menu = mb.addMenu("File")
        reload_action = QAction("Reload Session", self)
        reload_action.setShortcut(QKeySequence("Ctrl+R"))
        reload_action.triggered.connect(self._load_session)
        file_menu.addAction(reload_action)
        file_menu.addSeparator()
        quit_action = QAction("Quit", self)
        quit_action.setShortcut(QKeySequence("Ctrl+Q"))
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        # Settings menu
        settings_menu = mb.addMenu("Settings")
        settings_action = QAction("Configure Root Directory…", self)
        settings_action.triggered.connect(self._open_settings)
        settings_menu.addAction(settings_action)

        # Help menu
        help_menu = mb.addMenu("Help")
        about_action = QAction("About PyReps", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)
        shortcuts_action = QAction("Keyboard Shortcuts", self)
        shortcuts_action.triggered.connect(self._show_shortcuts)
        help_menu.addAction(shortcuts_action)

    # ── Session management ────────────────────────────────────────────────

    def _load_session(self):
        self.root_dir = Path(self.config.get("root_dir", str(DEFAULT_ROOT)))
        questions_dir = self.root_dir / "questions"
        progress_path = self.root_dir / "results" / "progress.json"

        if not questions_dir.exists():
            self._show_no_questions_dir(questions_dir)
            return

        self.sr = SpacedRepetitionManager(progress_path)

        all_questions = sorted(
            d.name for d in questions_dir.iterdir() if d.is_dir()
        )
        import random
        self.due_questions = [q for q in all_questions if self.sr.is_due(q)]
        random.shuffle(self.due_questions)

        self.current_index = 0
        self.submitted = False

        if not self.due_questions:
            next_date = self.sr.next_due_date()
            self._show_no_due_cards(next_date)
        else:
            self._load_question(self.current_index)

    def _load_question(self, index: int):
        if index >= len(self.due_questions):
            self._show_session_complete()
            return

        self.submitted = False
        question_id = self.due_questions[index]
        questions_dir = self.root_dir / "questions"
        question_dir = questions_dir / question_id
        working_dir = self.root_dir / "working"

        # Clear and repopulate working/
        if working_dir.exists():
            shutil.rmtree(working_dir)
        working_dir.mkdir(parents=True)

        for f in question_dir.iterdir():
            if f.is_file():
                dest_name = "solution.py" if f.name == "template.py" else f.name
                shutil.copy(f, working_dir / dest_name)

        # Load UI panels
        self.question_panel.load_question(question_id, question_dir / "question.md")
        self.editor.load_template(working_dir / "solution.py")
        self.results_panel.clear()

        display_name = question_id.replace("_", " ").title()
        self.bottom_bar.set_question(
            display_name, index + 1, len(self.due_questions)
        )
        self.status_bar.showMessage(f"Loaded: {question_id}")

    # ── Actions ───────────────────────────────────────────────────────────

    def _on_submit(self):
        if self.submitted:
            return
        if not self.due_questions or self.current_index >= len(self.due_questions):
            return
        question_id = self.due_questions[self.current_index]
        working_dir = self.root_dir / "working"
        solution_path = working_dir / "solution.py"

        # Save editor contents
        solution_path.write_text(self.editor.toPlainText())

        self.status_bar.showMessage("Running tests…")
        self.bottom_bar.submit_btn.setEnabled(False)

        self._runner = TestRunnerThread(working_dir)
        self._runner.finished.connect(lambda results, raw: self._on_tests_done(results, raw, question_id))
        self._runner.start()

    def _on_tests_done(self, results: list, raw: str, question_id: str):
        self.results_panel.show_results(results, raw)
        all_passed = results and all(r["status"] == "PASSED" for r in results)
        self.sr.record_result(question_id, correct=all_passed)
        self.submitted = True
        self.bottom_bar.show_next_button()
        status = "All tests passed!" if all_passed else "Some tests failed."
        self.status_bar.showMessage(status)

    def _on_skip(self):
        question_id = self.due_questions[self.current_index]
        self.sr.record_result(question_id, correct=False)
        self._advance()

    def _on_next(self):
        self._advance()

    def _advance(self):
        self.current_index += 1
        if self.current_index >= len(self.due_questions):
            self._show_session_complete()
        else:
            self.results_panel.clear()
            self._load_question(self.current_index)

    # ── Overlay helpers ───────────────────────────────────────────────────

    def _show_no_questions_dir(self, path: Path):
        self._replace_splitter_with(
            QLabel(
                f"<h2 style='color:#f07178'>Questions directory not found</h2>"
                f"<p style='color:#cdd3de'>Expected: <code>{path}</code></p>"
                f"<p style='color:#82aaff'>Go to <b>Settings → Configure Root Directory</b> to set your PyReps root.</p>"
            )
        )

    def _show_no_due_cards(self, next_date: str):
        self._replace_splitter_with(NoDueCardsWidget(next_date))

    def _show_session_complete(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl = QLabel("🏆  Session Complete!")
        lbl.setStyleSheet("font-size: 32px; font-weight: bold; color: #ffcb6b;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub = QLabel(f"You reviewed all {len(self.due_questions)} due cards.")
        sub.setStyleSheet("font-size: 16px; color: #82aaff; margin-top: 8px;")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(lbl)
        lay.addWidget(sub)
        self._replace_splitter_with(w)
        self.bottom_bar.progress_label.setText(
            f"{len(self.due_questions)} of {len(self.due_questions)} done"
        )

    def _replace_splitter_with(self, widget: QWidget):
        widget.setStyleSheet("background: #1a1f2e;")
        central = self.centralWidget()
        layout = central.layout()
        layout.replaceWidget(self.splitter, widget)
        self.splitter.hide()
        widget.show()

    # ── Settings / About ─────────────────────────────────────────────────

    def _open_settings(self):
        dlg = SettingsDialog(self.config.get("root_dir", str(DEFAULT_ROOT)), self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_path = dlg.get_path()
            self.config["root_dir"] = new_path
            save_config(self.config)
            self._load_session()

    def _show_about(self):
        QMessageBox.information(
            self,
            "About PyReps",
            "<b>PyReps</b> — Python Coding Flashcards<br><br>"
            "A spaced-repetition coding practice tool for Python interview prep.<br><br>"
            "Built with PyQt6.",
        )

    def _show_shortcuts(self):
        QMessageBox.information(
            self,
            "Keyboard Shortcuts",
            "<b>Ctrl+Enter</b> — Submit<br>"
            "<b>Ctrl+Right</b> — Next Card<br>"
            "<b>Ctrl+R</b> — Reload Session<br>"
            "<b>Ctrl+Q</b> — Quit",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("PyReps")

    # Force dark palette
    palette = app.palette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#1a1f2e"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#cdd3de"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#1a1f2e"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#252d3d"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#cdd3de"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#252d3d"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#cdd3de"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#3d4f6e"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    app.setPalette(palette)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
