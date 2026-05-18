def flatten(nested: list) -> list:
    """
    Given a nested list of arbitrary depth, return a flat list of all values.
    """
    result = []
    for item in nested:
        if isinstance(item, list):
            result.extend(flatten(item))
        else:
            result.append(item)
    return result
