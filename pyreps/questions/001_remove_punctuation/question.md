# Remove Punctuation

**Category:** String Manipulation

## Problem

Given a string, return it with all punctuation removed and converted to lowercase.

Punctuation includes any character that is not a letter or a digit or a space.

## Examples

**Example 1:**
```
Input:  s = "Hello, World!"
Output: "hello world"
```
Explanation: The comma and exclamation mark are punctuation and are removed. All letters are lowercased.

---

**Example 2:**
```
Input:  s = "It's a-maze-ing..."
Output: "its amazeing"
```
Explanation: The apostrophe, hyphens, and ellipsis are all punctuation and are stripped. Spaces between words are preserved.

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
