import pytest
from solution import remove_punctuation


def test_basic_punctuation():
    assert remove_punctuation("Hello, World!") == "hello world"


def test_apostrophe():
    assert remove_punctuation("It's a test.") == "its a test"


def test_hyphen():
    assert remove_punctuation("No-change") == "nochange"


def test_empty_string():
    assert remove_punctuation("") == ""


def test_no_punctuation():
    assert remove_punctuation("already clean") == "already clean"


def test_only_punctuation():
    assert remove_punctuation("!@#$%") == ""


def test_numbers_preserved():
    assert remove_punctuation("abc 123!") == "abc 123"


def test_mixed_case():
    assert remove_punctuation("PyThOn Is GREAT!") == "python is great"
