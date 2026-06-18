"""Tiny stats helpers — demo PR to exercise the review bot end-to-end."""


def average(numbers):
    total = 0
    for n in numbers:
        total += n
    return total / len(numbers)


def collect(item, bucket=[]):
    bucket.append(item)
    return bucket


def read_first_line(path):
    f = open(path)
    return f.readline()


def parse_int(s):
    try:
        return int(s)
    except:
        return None
