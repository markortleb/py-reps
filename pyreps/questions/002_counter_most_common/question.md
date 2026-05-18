# Counter Most Common

**Category:** Collections / Data Structures

## Problem

Given a list of words, return the single most common word using `collections.Counter`.

If the list is empty, return `None`.

## Examples

```python
most_common_word(["apple", "banana", "apple", "cherry"])  # → "apple"
most_common_word(["cat", "dog", "cat", "cat", "dog"])     # → "cat"
most_common_word(["only"])                                 # → "only"
most_common_word([])                                       # → None
```

## Constraints

- Input is a list of strings
- All words are lowercase
- Return a single string (the most common), or `None` for empty input
- If there is a tie, return any one of the tied words

## Hints

<details>
<summary>Hint 1</summary>
`collections.Counter` has a `most_common(n)` method that returns the top-n elements as `(element, count)` tuples.
</details>

<details>
<summary>Hint 2</summary>
`Counter.most_common(1)` returns a list with one tuple — index into it to get the word.
</details>
