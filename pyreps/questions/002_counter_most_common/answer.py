from collections import Counter
from typing import Optional


def most_common_word(words: list[str]) -> Optional[str]:
    """
    Given a list of words, return the most common word.
    """
    if not words:
        return None
    return Counter(words).most_common(1)[0][0]
