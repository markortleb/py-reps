import pytest
from solution import most_common_word


def test_basic_most_common():
    assert most_common_word(["apple", "banana", "apple", "cherry"]) == "apple"


def test_clear_winner():
    assert most_common_word(["cat", "dog", "cat", "cat", "dog"]) == "cat"


def test_single_element():
    assert most_common_word(["only"]) == "only"


def test_empty_list():
    assert most_common_word([]) is None


def test_all_same():
    assert most_common_word(["yes", "yes", "yes"]) == "yes"


def test_two_words():
    assert most_common_word(["a", "b", "a"]) == "a"


def test_long_list():
    words = ["x"] * 10 + ["y"] * 3 + ["z"] * 5
    assert most_common_word(words) == "x"
