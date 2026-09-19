from totals import column_total

SIMPLE = "name,amount\napples,2.5\npears,1.5\n"


def test_sums_second_column():
    assert column_total(SIMPLE, 1) == 4.0
