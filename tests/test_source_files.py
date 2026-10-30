"""Source file checks that run before any database work."""
import pytest

from olist_dbe import dq, load


def test_missing_file_is_reported_by_name(tmp_path):
    with pytest.raises(load.SourceFileError, match="olist_orders_dataset.csv"):
        load.inspect_files(tmp_path)


def test_source_files_are_the_reference_dataset(data_dir):
    """The pinned counts in this suite were measured on exactly these files."""
    assert load.manifest(load.inspect_files(data_dir)) == load.reference_manifest()


def test_translation_header_is_read_without_its_byte_order_mark(data_dir):
    files = {f.table: f for f in load.inspect_files(data_dir)}
    assert files["product_category_name_translation"].header == (
        "product_category_name", "product_category_name_english")


def test_every_dq_check_is_named_described_and_classified():
    checks = dq.discover()
    assert len({c.name for c in checks}) == len(checks)
    assert all(c.description for c in checks)
    assert {c.severity for c in checks} == {"blocking", "warning"}
