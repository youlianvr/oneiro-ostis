import pytest

from totals import column_total

QUOTED = 'name,amount\n"apples, red",2.5\n"pears, green",1.5\n'
HEADER_AND_TOTALS = "item,cost\none,1\n"


def test_quoted_commas_do_not_shift_columns():
    assert column_total(QUOTED, 1) == 4.0


def test_empty_data_rows():
    assert column_total("name,amount\n", 1) == 0.0


def test_missing_column_raises_index_error():
    with pytest.raises(IndexError):
        column_total(HEADER_AND_TOTALS, 5)


def test_returns_float():
    assert isinstance(column_total(HEADER_AND_TOTALS, 1), float)
