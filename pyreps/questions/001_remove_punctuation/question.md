# Remove Punctuation

**Category:** String Manipulation

## Problem

Given a string, return it with all punctuation removed and converted to lowercase.

Punctuation includes any character that is not a letter or a digit or a space.

## Examples

```python
remove_punctuation("Hello, World!")  # → "hello world"
remove_punctuation("It's a test.")   # → "its a test"
remove_punctuation("No-change")      # → "nochange"
remove_punctuation("")               # → ""
```

## Constraints

- Input is a string (may be empty)
- Preserve spaces between words
- Return lowercase output

## Hints

<details>
<summary>Hint 1</summary>
Consider using the `string` module — it has a `punctuation` constant.
</details>

<details>
<summary>Hint 2</summary>
You can use a list comprehension and `str.join` to filter characters.
</details>
