# Flatten Nested List

**Category:** Recursion / Lists

## Problem

Given a nested list of arbitrary depth, return a flat list containing all values.

The input may contain integers, strings, or further nested lists at any depth.

## Examples

**Example 1:**
```
Input:  nested = [1, [2, 3], [4, [5, 6]]]
Output: [1, 2, 3, 4, 5, 6]
```
Explanation: The top-level `1` is kept as-is. `[2, 3]` is one level deep and unwrapped. `[4, [5, 6]]` is two levels deep — `4` comes out directly and `[5, 6]` is unwrapped one more time.

---

**Example 2:**
```
Input:  nested = [[[1]], [2, [3, [4]]]]
Output: [1, 2, 3, 4]
```
Explanation: Recursion goes as deep as needed — `[[1]]` is unwrapped twice to yield `1`, and `[3, [4]]` is unwrapped until all values are flat.

## Constraints

- Input is a list (possibly empty) that may contain integers or further nested lists
- Output should preserve original order
- Use recursion

## Hints

<details>
<summary>Hint 1</summary>
Iterate over each item. If the item is a list, recurse into it. Otherwise, add it directly to the result.
</details>

<details>
<summary>Hint 2</summary>
Use `isinstance(item, list)` to check whether an element is a list.
</details>
