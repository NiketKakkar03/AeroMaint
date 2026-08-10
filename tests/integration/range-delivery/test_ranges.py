import pytest

from aeromaint_api.services.ranges import ByteRange, InvalidRange, parse_byte_range


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("bytes=0-0", ByteRange(0, 0)),
        ("bytes=2-", ByteRange(2, 9)),
        ("bytes=-3", ByteRange(7, 9)),
        ("bytes=4-99", ByteRange(4, 9)),
    ],
)
def test_single_byte_range_forms(header: str, expected: ByteRange) -> None:
    assert parse_byte_range(header, 10) == expected


@pytest.mark.parametrize(
    "header", ["bytes=", "bytes=3-2", "bytes=10-", "items=0-1", "bytes=0-1,4-5"]
)
def test_invalid_or_multi_ranges_are_rejected(header: str) -> None:
    with pytest.raises(InvalidRange):
        parse_byte_range(header, 10)
