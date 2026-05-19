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
import random
from datetime import date, timedelta
from pathlib import Path

import markdown2
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QSplitter, QTextBrowser, QPlainTextEdit, QLabel, QPushButton,
    QScrollArea, QFrame, QDialog, QLineEdit, QDialogButtonBox,
    QFileDialog, QMenuBar, QMessageBox, QStatusBar, QSizePolicy,
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
        keyword_fmt.setForeground(QColor("#569cd6"))
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
        builtin_fmt.setForeground(QColor("#dcdcaa"))
        builtins = [
            "print", "len", "range", "enumerate", "zip", "map", "filter",
            "sorted", "reversed", "list", "dict", "set", "tuple", "str",
            "int", "float", "bool", "type", "isinstance", "hasattr",
            "getattr", "setattr", "open", "super", "object", "self",
        ]
        for b in builtins:
            self._rules.append((re.compile(rf"\b{b}\b"), builtin_fmt))

        str_fmt = QTextCharFormat()
        str_fmt.setForeground(QColor("#ce9178"))
        self._rules.append((re.compile(r'"[^"\\]*(\\.[^"\\]*)*"'), str_fmt))
        self._rules.append((re.compile(r"'[^'\\]*(\\.[^'\\]*)*'"), str_fmt))

        comment_fmt = QTextCharFormat()
        comment_fmt.setForeground(QColor("#6a9955"))
        comment_fmt.setFontItalic(True)
        self._rules.append((re.compile(r"#[^\n]*"), comment_fmt))

        decorator_fmt = QTextCharFormat()
        decorator_fmt.setForeground(QColor("#c586c0"))
        self._rules.append((re.compile(r"@\w+"), decorator_fmt))

        number_fmt = QTextCharFormat()
        number_fmt.setForeground(QColor("#b5cea8"))
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
        self.setMinimumHeight(80)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)

        header = QLabel("Test Results")
        header.setStyleSheet("font-weight: bold; font-size: 14px; color: #d4d4d4;")
        layout.addWidget(header)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("QScrollArea { border: none; background: #1e1e1e; }")
        self.scroll.viewport().setStyleSheet("background: #1e1e1e;")
        self.results_container = QWidget()
        self.results_container.setStyleSheet("background: #1e1e1e;")
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
            lbl = QLabel("Could not parse test output:")
            lbl.setStyleSheet("color: #f44747; font-size: 12px; font-weight: bold; background: transparent;")
            self.results_layout.addWidget(lbl)
            raw_box = QPlainTextEdit(raw_output)
            raw_box.setReadOnly(True)
            raw_box.setStyleSheet(
                "background: #2d2d2d; color: #d4d4d4; border: 1px solid #3c3c3c; "
                "font-family: 'Courier New', monospace; font-size: 11px;"
            )
            raw_box.setMinimumHeight(180)
            self.results_layout.addWidget(raw_box)
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
            color = "#4ec9b0" if status == "PASSED" else "#f44747"

            # Strip the file path prefix for display
            name = r["name"]
            if "::" in name:
                name = name.split("::")[-1]

            title = QLabel(f"{icon} {name}")
            title.setStyleSheet(f"background: transparent; color: {color}; font-weight: bold; font-size: 12px;")
            title.setWordWrap(True)
            fl.addWidget(title)

            if r.get("detail"):
                detail = QLabel(r["detail"])
                detail.setStyleSheet("background: transparent; color: #9cdcfe; font-size: 11px; font-family: monospace;")
                detail.setWordWrap(True)
                fl.addWidget(detail)

            frame.setStyleSheet(
                f"QFrame {{ border: 1px solid {'#264f3c' if status == 'PASSED' else '#4f2626'}; "
                f"border-radius: 4px; background: {'#1a2e24' if status == 'PASSED' else '#2e1a1a'}; }}"
            )
            self.results_layout.addWidget(frame)

        color = "#4ec9b0" if passed == total else "#f44747"
        self.summary_label.setStyleSheet(f"font-weight: bold; color: {color}; font-size: 13px;")
        self.summary_label.setText(f"{passed}/{total} tests passed")


# ─────────────────────────────────────────────────────────────────────────────
# Question panel
# ─────────────────────────────────────────────────────────────────────────────

class QuestionPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        self.name_label = QLabel("")
        self.name_label.setStyleSheet(
            "font-weight: bold; font-size: 14px; color: #d4d4d4;"
        )
        self.name_label.setWordWrap(True)
        layout.addWidget(self.name_label)

        self.category_label = QLabel("")
        self.category_label.setStyleSheet(
            "font-size: 11px; color: #569cd6; font-style: italic; margin-bottom: 6px;"
        )
        layout.addWidget(self.category_label)

        self.text_browser = QTextBrowser()
        self.text_browser.setOpenExternalLinks(True)
        self.text_browser.setStyleSheet(
            "background: #1e1e1e; color: #d4d4d4; border: none; font-size: 13px;"
        )
        layout.addWidget(self.text_browser)

    def load_question(self, question_id: str, md_path: Path):
        # Parse name and category from markdown
        self.name_label.setText(question_id.replace("_", " ").title())
        self.category_label.setText("")

        if not md_path.exists():
            self.text_browser.setHtml("<p style='color:#f44747'>question.md not found.</p>")
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
            body {{ font-family: -apple-system, sans-serif; font-size: 13px; color: #d4d4d4; }}
            h1, h2, h3 {{ color: #569cd6; }}
            code {{ background: #2d2d2d; color: #ce9178; padding: 1px 4px;
                    border-radius: 3px; font-family: 'Courier New', monospace; }}
            pre {{ background: #2d2d2d; padding: 10px; border-radius: 4px;
                   overflow-x: auto; font-family: 'Courier New', monospace; }}
            strong {{ color: #dcdcaa; }}
            details {{ margin: 6px 0; }}
            summary {{ cursor: pointer; color: #9cdcfe; }}
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
            "background: #1e1e1e; color: #d4d4d4; border: none; "
            "selection-background-color: #264f78;"
        )
        self._highlighter = PythonHighlighter(self.document())

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Tab:
            self.insertPlainText("    ")
        elif event.key() == Qt.Key.Key_Backtab:
            cursor = self.textCursor()
            cursor.movePosition(cursor.MoveOperation.StartOfLine, cursor.MoveMode.KeepAnchor)
            sel = cursor.selectedText()
            if sel.startswith("    "):
                cursor.movePosition(cursor.MoveOperation.StartOfLine)
                for _ in range(4):
                    cursor.deleteChar()
        else:
            super().keyPressEvent(event)

    def load_template(self, template_path: Path):
        if template_path.exists():
            self.setPlainText(template_path.read_text())
        else:
            self.setPlainText("# template.py not found\n")


# ─────────────────────────────────────────────────────────────────────────────
# Collapsible solution panel
# ─────────────────────────────────────────────────────────────────────────────

class CollapsibleSection(QWidget):
    toggled = pyqtSignal(bool)  # True = expanded

    HEADER_H = 36

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(self.HEADER_H)
        self.setMaximumHeight(self.HEADER_H)  # collapsed by default

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.toggle_btn = QPushButton("▶   Show Solution")
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.setFixedHeight(self.HEADER_H)
        self.toggle_btn.setStyleSheet(
            "QPushButton { background: #252526; color: #dcdcaa; border: none; "
            "border-top: 1px solid #3c3c3c; border-bottom: 1px solid #3c3c3c; "
            "font-size: 13px; font-weight: bold; text-align: left; padding-left: 12px; }"
            "QPushButton:hover { background: #2d2d2d; }"
            "QPushButton:checked { color: #4ec9b0; }"
        )
        self.toggle_btn.toggled.connect(self._on_toggle)
        layout.addWidget(self.toggle_btn)

        self.content = QWidget()
        self.content.setStyleSheet("background: #1e1e1e;")
        cl = QVBoxLayout(self.content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)

        self.answer_editor = CodeEditor()
        self.answer_editor.setReadOnly(True)
        self.answer_editor.setStyleSheet(
            "background: #1e1e1e; color: #9cdcfe; border: none; "
            "selection-background-color: #264f78;"
        )
        cl.addWidget(self.answer_editor)

        self.content.setVisible(False)
        layout.addWidget(self.content)

    def _on_toggle(self, checked: bool):
        self.content.setVisible(checked)
        self.toggle_btn.setText(
            "▼   Hide Solution" if checked else "▶   Show Solution"
        )
        if checked:
            self.setMaximumHeight(16777215)
        else:
            self.setMaximumHeight(self.HEADER_H)
        self.toggled.emit(checked)

    def collapse(self):
        self.toggle_btn.setChecked(False)

    def load_answer(self, path: Path):
        if path.exists():
            self.answer_editor.setPlainText(path.read_text())
        else:
            self.answer_editor.setPlainText("# answer.py not found for this question\n")


# ─────────────────────────────────────────────────────────────────────────────
# Bottom bar
# ─────────────────────────────────────────────────────────────────────────────

class BottomBar(QWidget):
    submit_clicked = pyqtSignal()
    skip_clicked = pyqtSignal()
    next_clicked = pyqtSignal()
    retry_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(52)
        self.setStyleSheet("background: #252526; border-top: 1px solid #3c3c3c;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(10)

        self.question_label = QLabel("No question loaded")
        self.question_label.setStyleSheet("color: #569cd6; font-size: 13px;")
        layout.addWidget(self.question_label)

        layout.addStretch()

        self.progress_label = QLabel("")
        self.progress_label.setStyleSheet("color: #858585; font-size: 12px;")
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

        self.retry_btn = QPushButton("↺ Retry")
        self.retry_btn.setStyleSheet(_btn_style("#5a3e00", "#7a5500", "#3a2800"))
        self.retry_btn.setFixedHeight(32)
        self.retry_btn.setVisible(False)
        self.retry_btn.clicked.connect(self.retry_clicked)
        layout.addWidget(self.retry_btn)

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
        self.retry_btn.setVisible(False)
        self.submit_btn.setEnabled(True)

    def show_next_button(self):
        self.next_btn.setVisible(True)
        self.retry_btn.setVisible(True)
        self.submit_btn.setEnabled(False)

    def show_submit_for_retry(self):
        self.submit_btn.setEnabled(True)
        self.retry_btn.setVisible(False)


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
        msg.setStyleSheet("font-size: 28px; font-weight: bold; color: #4ec9b0;")
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(msg)

        sub = QLabel(f"No cards are due today.\nNext review: {next_date}")
        sub.setStyleSheet("font-size: 16px; color: #569cd6; margin-top: 8px;")
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
        self._overlay_widget: QWidget | None = None
        self._sr_recorded: bool = False

        self._setup_ui()
        self._setup_menu()
        self._load_session()

    # ── UI construction ───────────────────────────────────────────────────

    def _setup_ui(self):
        self.setStyleSheet("background: #1e1e1e; color: #d4d4d4;")

        central = QWidget()
        self.setCentralWidget(central)
        self._content_widget = central
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Single vertical splitter: question / solution / editor / results
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.setHandleWidth(2)
        self.splitter.setStyleSheet("QSplitter::handle { background: #3c3c3c; }")

        self.question_panel = QuestionPanel()
        self.splitter.addWidget(self.question_panel)

        self.collapsible_answer = CollapsibleSection()
        self.collapsible_answer.toggled.connect(self._on_solution_toggle)
        self.splitter.addWidget(self.collapsible_answer)
        self.splitter.setCollapsible(1, False)

        self.editor = CodeEditor()
        self.splitter.addWidget(self.editor)

        self.results_panel = ResultsPanel()
        self.splitter.addWidget(self.results_panel)

        self.splitter.setStretchFactor(0, 2)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setStretchFactor(2, 3)
        self.splitter.setStretchFactor(3, 1)

        root_layout.addWidget(self.splitter, 1)

        self.bottom_bar = BottomBar()
        self.bottom_bar.submit_clicked.connect(self._on_submit)
        self.bottom_bar.skip_clicked.connect(self._on_skip)
        self.bottom_bar.next_clicked.connect(self._on_next)
        self.bottom_bar.retry_clicked.connect(self._on_retry)
        root_layout.addWidget(self.bottom_bar)

        # Status bar
        self.status_bar = QStatusBar()
        self.status_bar.setStyleSheet(
            "background: #007acc; color: #ffffff; font-size: 11px; border-top: none;"
        )
        self.setStatusBar(self.status_bar)

    def _setup_menu(self):
        mb = self.menuBar()
        mb.setStyleSheet(
            "QMenuBar { background: #252526; color: #d4d4d4; }"
            "QMenuBar::item:selected { background: #2d2d2d; }"
            "QMenu { background: #252526; color: #d4d4d4; border: 1px solid #3c3c3c; }"
            "QMenu::item:selected { background: #094771; }"
        )

        # File menu
        file_menu = mb.addMenu("File")
        reload_action = QAction("Reload Session", self)
        reload_action.setShortcut(QKeySequence("Ctrl+R"))
        reload_action.triggered.connect(self._load_session)
        file_menu.addAction(reload_action)
        shuffle_action = QAction("Shuffle All Cards", self)
        shuffle_action.setShortcut(QKeySequence("Ctrl+Shift+R"))
        shuffle_action.triggered.connect(self._shuffle_all)
        file_menu.addAction(shuffle_action)
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
        self._restore_splitter()
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
        self.collapsible_answer.load_answer(working_dir / "answer.py")
        self.collapsible_answer.collapse()
        self.results_panel.clear()
        self._sr_recorded = False

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
        if all_passed:
            if not self._sr_recorded:
                self.sr.record_result(question_id, correct=True)
                self._sr_recorded = True
            self.submitted = True
            self.bottom_bar.show_next_button()
            self.status_bar.showMessage("All tests passed!")
        else:
            self.bottom_bar.submit_btn.setEnabled(True)
            self.status_bar.showMessage("Some tests failed — fix your code and resubmit.")

    def _on_solution_toggle(self, expanded: bool):
        sizes = self.splitter.sizes()
        if expanded:
            give = max(200, self.splitter.height() // 4)
            take = min(give, sizes[2] - 150)
            sizes[1] = sizes[1] - CollapsibleSection.HEADER_H + take
            sizes[2] = max(150, sizes[2] - take)
        else:
            sizes[2] += sizes[1] - CollapsibleSection.HEADER_H
            sizes[1] = CollapsibleSection.HEADER_H
        self.splitter.setSizes(sizes)

    def _on_retry(self):
        working_dir = self.root_dir / "working"
        self.editor.load_template(working_dir / "solution.py")
        self.results_panel.clear()
        self.submitted = False
        self.bottom_bar.show_submit_for_retry()
        self.status_bar.showMessage("Editor reset — give it another shot!")

    def _on_skip(self):
        question_id = self.due_questions[self.current_index]
        if not self.submitted:
            self.sr.record_result(question_id, correct=False)
        self._advance()

    def _on_next(self):
        self._advance()

    def _advance(self):
        self.current_index += 1
        self.submitted = False
        if self.current_index >= len(self.due_questions):
            self._show_session_complete()
        else:
            self.results_panel.clear()
            self._load_question(self.current_index)

    def _shuffle_all(self):
        self.root_dir = Path(self.config.get("root_dir", str(DEFAULT_ROOT)))
        questions_dir = self.root_dir / "questions"
        progress_path = self.root_dir / "results" / "progress.json"
        if not questions_dir.exists():
            self._show_no_questions_dir(questions_dir)
            return
        self.sr = SpacedRepetitionManager(progress_path)
        all_questions = sorted(d.name for d in questions_dir.iterdir() if d.is_dir())
        self.due_questions = list(all_questions)
        random.shuffle(self.due_questions)
        self.current_index = 0
        self.submitted = False
        self._restore_splitter()
        self._load_question(self.current_index)

    # ── Overlay helpers ───────────────────────────────────────────────────

    def _show_no_questions_dir(self, path: Path):
        self._replace_splitter_with(
            QLabel(
                f"<h2 style='color:#f44747'>Questions directory not found</h2>"
                f"<p style='color:#d4d4d4'>Expected: <code>{path}</code></p>"
                f"<p style='color:#569cd6'>Go to <b>Settings → Configure Root Directory</b> to set your PyReps root.</p>"
            )
        )

    def _show_no_due_cards(self, next_date: str):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon = QLabel("🎉")
        icon.setStyleSheet("font-size: 64px;")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(icon)
        msg = QLabel("All caught up!")
        msg.setStyleSheet("font-size: 28px; font-weight: bold; color: #4ec9b0;")
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(msg)
        sub = QLabel(f"No cards are due today.\nNext review: {next_date}")
        sub.setStyleSheet("font-size: 16px; color: #569cd6; margin-top: 8px;")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(sub)
        lay.addSpacing(24)
        btn = QPushButton("Shuffle All Cards & Restart")
        btn.setStyleSheet(_btn_style("#6a1b9a", "#8e24aa", "#4a148c"))
        btn.setFixedHeight(36)
        btn.setFixedWidth(240)
        btn.clicked.connect(self._shuffle_all)
        lay.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)
        self._replace_splitter_with(w)

    def _show_session_complete(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl = QLabel("🏆  Session Complete!")
        lbl.setStyleSheet("font-size: 32px; font-weight: bold; color: #dcdcaa;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub = QLabel(f"You reviewed all {len(self.due_questions)} due cards.")
        sub.setStyleSheet("font-size: 16px; color: #569cd6; margin-top: 8px;")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(lbl)
        lay.addWidget(sub)
        lay.addSpacing(24)
        btn = QPushButton("Shuffle All Cards & Restart")
        btn.setStyleSheet(_btn_style("#6a1b9a", "#8e24aa", "#4a148c"))
        btn.setFixedHeight(36)
        btn.setFixedWidth(240)
        btn.clicked.connect(self._shuffle_all)
        lay.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)
        self._replace_splitter_with(w)
        self.bottom_bar.progress_label.setText(
            f"{len(self.due_questions)} of {len(self.due_questions)} done"
        )

    def _replace_splitter_with(self, widget: QWidget):
        widget.setStyleSheet("background: #1e1e1e;")
        layout = self._content_widget.layout()
        if self._overlay_widget is not None:
            layout.replaceWidget(self._overlay_widget, widget)
            self._overlay_widget.deleteLater()
        else:
            layout.replaceWidget(self.splitter, widget)
            self.splitter.hide()
        self._overlay_widget = widget
        widget.show()

    def _restore_splitter(self):
        if self._overlay_widget is not None:
            layout = self._content_widget.layout()
            layout.replaceWidget(self._overlay_widget, self.splitter)
            self._overlay_widget.deleteLater()
            self._overlay_widget = None
            self.splitter.show()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w = self.centralWidget().width()
        m = max(24, int(w * 0.10))
        self.centralWidget().layout().setContentsMargins(m, 0, m, 0)

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
            "<b>Ctrl+Shift+R</b> — Shuffle All Cards<br>"
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
    palette.setColor(QPalette.ColorRole.Window, QColor("#1e1e1e"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#d4d4d4"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#1e1e1e"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#252526"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#d4d4d4"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#3c3c3c"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#d4d4d4"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#264f78"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    app.setPalette(palette)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
