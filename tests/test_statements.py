"""The two layout rules every generated statement follows."""

from mason.statements import listed, statement


def test_a_statement_keeps_its_lines_in_order_and_drops_the_ones_that_dont_apply():
    assert statement("SELECT *", None, "FROM t", None) == "SELECT *\nFROM t;"


def test_a_statement_ends_in_one_semicolon_and_nothing_after_it():
    assert statement("SELECT 1").endswith("1;")


def test_listed_items_sit_one_per_line_indented_and_comma_separated():
    assert listed(["a", "b", "c"]) == "  a,\n  b,\n  c"


def test_nothing_trails_a_single_listed_item():
    assert listed(["a"]) == "  a"
