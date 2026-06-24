"""Tiny stats helpers — demo PR to exercise the review bot end-to-end."""


def average(numbers):
    total = 0
    count = 0
    for n in numbers:
        total += n
        count += 1
    if count == 0:
        raise ValueError("average() requires at least one number")
    return total / count


def collect(item, bucket=None):
    if bucket is None:
        bucket = []
    bucket.append(item)
    return bucket


def read_first_line(path):
    with open(path, encoding="utf-8") as f:
        return f.readline().rstrip("\n")


def parse_int(s):
    try:
        return int(s)
    except (ValueError, TypeError):
        return None
