"""Tiny stats helpers — demo PR to exercise the review bot end-to-end."""


def average(numbers):
    total = 0
    for n in numbers:
        total += n
    if not numbers:
        raise ValueError("average() requires at least one number")
    return total / len(numbers)


def collect(item, bucket=None):
    if bucket is None:
        bucket = []
    bucket.append(item)
    return bucket


def read_first_line(path):
    with open(path, encoding="utf-8") as f:
        return f.readline()


def parse_int(s):
    try:
        return int(s)
    except (ValueError, TypeError):
        return None
