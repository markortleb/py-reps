# Counter Most Common

**Category:** Collections / Data Structures

## Problem

Given a list of words, return the single most common word using `collections.Counter`.

If the list is empty, return `None`.

## Examples

**Example 1:**
```
Input:  words = ["apple", "banana", "apple", "cherry", "banana", "apple"]
Output: "apple"
```
Explanation: "apple" appears 3 times, "banana" 2 times, and "cherry" 1 time. "apple" is the most frequent.

---

**Example 2:**
```
Input:  words = ["cat", "dog", "cat", "dog", "dog"]
Output: "dog"
```
Explanation: "dog" appears 3 times and "cat" appears 2 times, so "dog" is returned.

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
