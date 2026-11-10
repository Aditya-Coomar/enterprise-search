from src.schemas.contracts import Element


def reading_order(elements: list[Element], width: float) -> list[Element]:
    """Read clear two-column bands separately, retaining spanning elements as separators."""
    ordered = sorted(elements, key=lambda e: (round(e.bbox[1], 1), e.bbox[0]))
    result = []
    left = []
    right = []

    def flush():
        if (
            len(left) >= 2
            and len(right) >= 2
            and min(left[-1].bbox[3], right[-1].bbox[3]) > max(left[0].bbox[1], right[0].bbox[1])
        ):
            result.extend(left)
            result.extend(right)
        else:
            result.extend(sorted(left + right, key=lambda e: (round(e.bbox[1], 1), e.bbox[0])))
        left.clear()
        right.clear()

    for element in ordered:
        if element.bbox[2] <= width * 0.49:
            left.append(element)
        elif element.bbox[0] >= width * 0.51:
            right.append(element)
        else:
            flush()
            result.append(element)
    flush()
    return result
