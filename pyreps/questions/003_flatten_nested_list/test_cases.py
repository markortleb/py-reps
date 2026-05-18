import pytest
from solution import flatten


def test_basic_nested():
    assert flatten([1, [2, 3], [4, [5, 6]]]) == [1, 2, 3, 4, 5, 6]


def test_deeply_nested():
    assert flatten([[1, 2], [3, [4, [5]]]]) == [1, 2, 3, 4, 5]


def test_empty_list():
    assert flatten([]) == []


def test_already_flat():
    assert flatten([1, 2, 3]) == [1, 2, 3]


def test_single_deep_element():
    assert flatten([[[[[42]]]]]) == [42]


def test_mixed_depth():
    assert flatten([1, [2, [3, [4]]], 5]) == [1, 2, 3, 4, 5]


def test_nested_empty_lists():
    assert flatten([[], [1, 2], []]) == [1, 2]


def test_strings():
    assert flatten(["a", ["b", "c"], ["d", ["e"]]]) == ["a", "b", "c", "d", "e"]
