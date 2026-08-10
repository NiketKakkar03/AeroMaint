import hashlib
import re
from dataclasses import dataclass

_RANGE = re.compile(r"bytes=(\d*)-(\d*)$")


class InvalidRange(ValueError):
    pass


@dataclass(frozen=True)
class ByteRange:
    start: int
    end: int

    @property
    def length(self) -> int:
        return self.end - self.start + 1


def parse_byte_range(value: str, size: int) -> ByteRange:
    match = _RANGE.fullmatch(value.strip())
    if match is None or size < 1:
        raise InvalidRange(value)
    first, last = match.groups()
    if not first:
        suffix = int(last)
        if suffix < 1:
            raise InvalidRange(value)
        return ByteRange(max(0, size - suffix), size - 1)
    start = int(first)
    end = size - 1 if not last else int(last)
    if start >= size or end < start:
        raise InvalidRange(value)
    return ByteRange(start, min(end, size - 1))


def strong_etag(data: bytes) -> str:
    return f'"{hashlib.sha256(data).hexdigest()}"'
