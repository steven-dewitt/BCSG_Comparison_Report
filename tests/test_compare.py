import math

import pytest

from bcsg_compare import SelectionError, build_comparison, select_tests
from bcsg_compare.compare import sort_labels


def test_explicit_order_is_kept(db):
    assert select_tests(db, ["26-01", "16-01", "25-09"]) == ["26-01", "16-01", "25-09"]


def test_repeated_id_selects_every_run_and_label_selects_one(db):
    assert select_tests(db, ["23-13"]) == ["23-13 (1)", "23-13 (2)"]
    assert select_tests(db, ["23-13 (2)"]) == ["23-13 (2)"]


def test_wildcards_and_dedupe(db):
    assert select_tests(db, ["2*", "25-09"]) == ["23-13 (1)", "23-13 (2)", "25-09", "25-12", "26-01"]


def test_filters(db):
    assert select_tests(db, grades=["t479"]) == ["16-01", "16-02"]
    assert select_tests(db, notes="dc") == ["25-09", "25-12", "26-01"]
    assert select_tests(db, all_tests=True, last=2) == ["25-12", "26-01"]


def test_unknown_test_suggests_close_match(db):
    with pytest.raises(SelectionError, match="did you mean 26-01"):
        select_tests(db, ["26-1"])


def test_nothing_selected(db):
    with pytest.raises(SelectionError):
        select_tests(db)
    with pytest.raises(SelectionError):
        select_tests(db, grades=["XYZ"])


def test_sort(db):
    labels = ["26-01", "16-02", "23-13 (2)", "16-01"]
    assert sort_labels(db, labels, "test") == ["16-01", "16-02", "23-13 (2)", "26-01"]
    assert sort_labels(db, labels, "grade")[0] == "23-13 (2)"


def test_empty_segments_dropped(db):
    cmp = build_comparison(db, ["25-09", "26-01"])
    assert cmp.segments == [1, 2, 3, 6, 7, 8]
    assert cmp.dropped_segments == [4, 5]
    cmp = build_comparison(db, ["25-09", "26-01"], keep_empty_segments=True)
    assert cmp.segments == list(range(1, 9))


def test_explicit_segments(db):
    cmp = build_comparison(db, ["16-01"], segments=[8, 1])
    assert cmp.segments == [1, 8]
    with pytest.raises(SelectionError, match="Unknown segment"):
        build_comparison(db, ["16-01"], segments=[12])


def test_baseline_is_added_and_pct_computed(db):
    cmp = build_comparison(db, ["26-01"], baseline="25-09")
    assert cmp.labels == ["25-09", "26-01"]
    pct = cmp.pct_vs_baseline("Riser Wear")
    base = cmp.table("Riser Wear").loc["25-09", 1]
    assert pct.at["26-01", 1] == pytest.approx(cmp.table("Riser Wear").loc["26-01", 1] / base - 1)
    assert pct.at["25-09", 1] == 0
    assert math.isnan(pct.at["26-01", 7])


def test_ambiguous_baseline(db):
    with pytest.raises(SelectionError, match="several"):
        build_comparison(db, ["16-01"], baseline="23-13")


def test_group_by_auto(db):
    assert build_comparison(db, db.labels[:3]).group_by == "segment"
    from bcsg_compare import compare
    old = compare.AUTO_GROUP_BY_TEST_ABOVE
    compare.AUTO_GROUP_BY_TEST_ABOVE = 2
    try:
        assert build_comparison(db, db.labels[:3]).group_by == "test"
    finally:
        compare.AUTO_GROUP_BY_TEST_ABOVE = old


def test_summary_means_ignore_missing(db):
    cmp = build_comparison(db, ["26-01"])
    expected = sum(cmp.table("Riser Wear").loc["26-01", s] for s in (1, 2, 3, 6)) / 4
    assert cmp.summary().at["26-01", "Riser Wear mean"] == pytest.approx(expected)
    assert cmp.summary().at["26-01", "Segments with data"] == 4
