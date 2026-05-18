# Flatten Nested List

**Category:** Recursion / Lists

## Problem

Given a nested list of arbitrary depth, return a flat list containing all values.

The input may contain integers, strings, or further nested lists at any depth.

## Examples

```python
flatten([1, [2, 3], [4, [5, 6]]])       # → [1, 2, 3, 4, 5, 6]
flatten([[1, 2], [3, [4, [5]]]])         # → [1, 2, 3, 4, 5]
flatten([])                              # → []
flatten([1, 2, 3])                       # → [1, 2, 3]
flatten([[[[[42]]]]])                    # → [42]
```

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
