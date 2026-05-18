import string


def remove_punctuation(s: str) -> str:
    """
    Given a string, return it with all punctuation removed and lowercased.
    """
    return "".join(ch for ch in s if ch not in string.punctuation).lower()
