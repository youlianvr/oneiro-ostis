"""Sum a numeric column of CSV text."""


def column_total(text, index):
    """Return the sum of column `index` over all data rows of `text`."""
    total = 0
    for line in text.strip().splitlines()[1:]:
        cells = line.split(",")
        total += float(cells[index])
    return total
