"""Small deterministic reader for unchunked ROS 2 MCAP captures."""

from __future__ import annotations

import hashlib
import itertools
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ADAPTER_VERSION = "1.0.0"
MAGIC = b"\x89MCAP0\r\n"
SUPPORTED_TYPES = {
    "sensor_msgs/msg/Image": "image",
    "sensor_msgs/msg/Imu": "imu",
    "geometry_msgs/msg/PoseStamped": "pose",
    "aeromaint_msgs/msg/Event": "event",
}


class MCAPValidationError(ValueError):
    """The MCAP source cannot be safely converted to canonical records."""


@dataclass(frozen=True)
class Message:
    log_time_ns: int
    publish_time_ns: int
    sequence: int
    value: dict[str, Any]


@dataclass(frozen=True)
class Topic:
    name: str
    type: str
    kind: str
    frame_ids: tuple[str, ...]
    units: dict[str, str]
    messages: tuple[Message, ...]


@dataclass(frozen=True)
class MCAPSource:
    path: Path
    source_sha256: str
    profile: str
    library: str
    topics: tuple[Topic, ...]
    unsupported: tuple[dict[str, str], ...]
    source_epoch_ns: int


class _Cursor:
    def __init__(self, data: bytes, context: str) -> None:
        self.data, self.offset, self.context = data, 0, context

    def take(self, size: int) -> bytes:
        end = self.offset + size
        if end > len(self.data):
            raise MCAPValidationError(f"{self.context}: truncated record")
        value, self.offset = self.data[self.offset : end], end
        return value

    def u16(self) -> int:
        return int(struct.unpack("<H", self.take(2))[0])

    def u32(self) -> int:
        return int(struct.unpack("<I", self.take(4))[0])

    def u64(self) -> int:
        return int(struct.unpack("<Q", self.take(8))[0])

    def string(self) -> str:
        try:
            return self.take(self.u32()).decode("utf-8")
        except UnicodeDecodeError as error:
            raise MCAPValidationError(f"{self.context}: invalid UTF-8 string") from error

    def blob(self) -> bytes:
        return self.take(self.u32())


class _CDR:
    def __init__(self, data: bytes, context: str) -> None:
        if len(data) < 4 or data[:2] not in (b"\x00\x01", b"\x00\x03"):
            raise MCAPValidationError(f"{context}: expected little-endian CDR encapsulation")
        self.data, self.offset, self.context = data, 4, context

    def align(self, alignment: int) -> None:
        self.offset += (-self.offset) % alignment

    def unpack(self, fmt: str, alignment: int) -> Any:
        self.align(alignment)
        size = struct.calcsize(fmt)
        if self.offset + size > len(self.data):
            raise MCAPValidationError(f"{self.context}: truncated CDR payload")
        result = struct.unpack_from("<" + fmt, self.data, self.offset)[0]
        self.offset += size
        return result

    def u8(self) -> int:
        return int(self.unpack("B", 1))

    def u32(self) -> int:
        return int(self.unpack("I", 4))

    def i32(self) -> int:
        return int(self.unpack("i", 4))

    def f64(self) -> float:
        return float(self.unpack("d", 8))

    def string(self) -> str:
        size = self.u32()
        if size == 0 or self.offset + size > len(self.data):
            raise MCAPValidationError(f"{self.context}: invalid CDR string")
        raw, self.offset = self.data[self.offset : self.offset + size], self.offset + size
        if raw[-1:] != b"\0":
            raise MCAPValidationError(f"{self.context}: CDR string is not NUL terminated")
        return raw[:-1].decode("utf-8")

    def bytes(self) -> bytes:
        size = self.u32()
        end = self.offset + size
        if end > len(self.data):
            raise MCAPValidationError(f"{self.context}: truncated CDR byte sequence")
        value, self.offset = self.data[self.offset : end], end
        return value


def _header(cdr: _CDR) -> tuple[int, str]:
    seconds, nanoseconds, frame_id = cdr.i32(), cdr.u32(), cdr.string()
    return seconds * 1_000_000_000 + nanoseconds, frame_id


def _vector(cdr: _CDR) -> list[float]:
    return [cdr.f64(), cdr.f64(), cdr.f64()]


def _quaternion(cdr: _CDR) -> list[float]:
    return [cdr.f64(), cdr.f64(), cdr.f64(), cdr.f64()]


def _decode(type_name: str, data: bytes, context: str) -> dict[str, Any]:
    cdr = _CDR(data, context)
    stamp_ns, frame_id = _header(cdr)
    if type_name == "sensor_msgs/msg/Image":
        height, width, encoding = cdr.u32(), cdr.u32(), cdr.string()
        is_bigendian, step, pixels = cdr.u8(), cdr.u32(), cdr.bytes()
        if len(pixels) != height * step:
            raise MCAPValidationError(
                f"{context}: image data length {len(pixels)} does not match "
                f"height*step {height * step}"
            )
        return {
            "stamp_ns": stamp_ns,
            "frame_id": frame_id,
            "height": height,
            "width": width,
            "encoding": encoding,
            "is_bigendian": is_bigendian,
            "step": step,
            "data": pixels.hex(),
        }
    if type_name == "sensor_msgs/msg/Imu":
        orientation = _quaternion(cdr)
        orientation_covariance = [cdr.f64() for _ in range(9)]
        angular_velocity = _vector(cdr)
        angular_velocity_covariance = [cdr.f64() for _ in range(9)]
        linear_acceleration = _vector(cdr)
        linear_acceleration_covariance = [cdr.f64() for _ in range(9)]
        return {
            "stamp_ns": stamp_ns,
            "frame_id": frame_id,
            "orientation_xyzw": orientation,
            "orientation_covariance": orientation_covariance,
            "angular_velocity_rad_s": angular_velocity,
            "angular_velocity_covariance": angular_velocity_covariance,
            "linear_acceleration_m_s2": linear_acceleration,
            "linear_acceleration_covariance": linear_acceleration_covariance,
        }
    if type_name == "geometry_msgs/msg/PoseStamped":
        return {
            "stamp_ns": stamp_ns,
            "frame_id": frame_id,
            "position_m": _vector(cdr),
            "orientation_xyzw": _quaternion(cdr),
        }
    if type_name == "aeromaint_msgs/msg/Event":
        return {
            "stamp_ns": stamp_ns,
            "frame_id": frame_id,
            "severity": cdr.string(),
            "message": cdr.string(),
        }
    raise MCAPValidationError(f"{context}: unsupported ROS 2 schema {type_name!r}")


def _metadata(cursor: _Cursor) -> dict[str, str]:
    result: dict[str, str] = {}
    size = cursor.u32()
    end = cursor.offset + size
    while cursor.offset < end:
        result[cursor.string()] = cursor.string()
    if cursor.offset != end:
        raise MCAPValidationError(f"{cursor.context}: malformed metadata map")
    return result


class MCAPAdapter:
    """Parse selected unchunked ROS 2 CDR topics while reporting unsupported schemas."""

    def read(self, source: Path) -> MCAPSource:
        data = source.read_bytes()
        if len(data) < 16 or data[:8] != MAGIC or data[-8:] != MAGIC:
            raise MCAPValidationError(f"{source}: invalid MCAP magic")
        schemas: dict[int, tuple[str, str]] = {}
        channels: dict[int, tuple[int, str, str, dict[str, str]]] = {}
        messages: dict[int, list[Message]] = {}
        profile = library = ""
        cursor = _Cursor(data[8:-8], str(source))
        while cursor.offset < len(cursor.data):
            opcode, length = cursor.take(1)[0], cursor.u64()
            body = _Cursor(cursor.take(length), f"{source}: opcode 0x{opcode:02x}")
            if opcode == 0x01:
                profile, library = body.string(), body.string()
            elif opcode == 0x03:
                schema_id, name, encoding = body.u16(), body.string(), body.string()
                body.blob()
                schemas[schema_id] = (name, encoding)
            elif opcode == 0x04:
                channel_id, schema_id = body.u16(), body.u16()
                channels[channel_id] = (schema_id, body.string(), body.string(), _metadata(body))
            elif opcode == 0x05:
                channel_id, sequence, log_time, publish_time = (
                    body.u16(),
                    body.u32(),
                    body.u64(),
                    body.u64(),
                )
                if channel_id not in channels:
                    raise MCAPValidationError(
                        f"{body.context}: references unknown channel {channel_id}"
                    )
                schema_id, topic, encoding, _ = channels[channel_id]
                if schema_id not in schemas:
                    raise MCAPValidationError(
                        f"topic {topic!r}: references unknown schema {schema_id}"
                    )
                type_name, schema_encoding = schemas[schema_id]
                if type_name in SUPPORTED_TYPES:
                    if encoding != "cdr" or schema_encoding != "ros2msg":
                        raise MCAPValidationError(
                            f"topic {topic!r} ({type_name}): expected ros2msg schema "
                            "with cdr messages; "
                            f"got schema={schema_encoding!r}, message={encoding!r}"
                        )
                    value = _decode(
                        type_name, body.take(len(body.data) - body.offset), f"topic {topic!r}"
                    )
                    messages.setdefault(channel_id, []).append(
                        Message(log_time, publish_time, sequence, value)
                    )
            elif opcode == 0x06:
                raise MCAPValidationError(
                    f"{source}: chunked MCAP is not supported; rewrite with unchunked records"
                )
        if profile != "ros2":
            raise MCAPValidationError(f"{source}: expected MCAP profile 'ros2', got {profile!r}")
        topics: list[Topic] = []
        unsupported: list[dict[str, str]] = []
        for channel_id, (schema_id, topic, encoding, _) in sorted(channels.items()):
            if schema_id not in schemas:
                raise MCAPValidationError(f"topic {topic!r}: references unknown schema {schema_id}")
            type_name, schema_encoding = schemas[schema_id]
            if type_name not in SUPPORTED_TYPES:
                unsupported.append(
                    {
                        "topic": topic,
                        "schema": type_name,
                        "schema_encoding": schema_encoding,
                        "message_encoding": encoding,
                        "diagnostic": (
                            f"unsupported ROS 2 schema {type_name!r} on topic {topic!r}; "
                            "supported: " + ", ".join(sorted(SUPPORTED_TYPES))
                        ),
                    }
                )
                continue
            records = messages.get(channel_id, [])
            if not records:
                continue
            if any(
                current.publish_time_ns < previous.publish_time_ns
                for previous, current in itertools.pairwise(records)
            ):
                raise MCAPValidationError(
                    f"topic {topic!r}: publish timestamps must be nondecreasing"
                )
            frames = tuple(sorted({str(item.value["frame_id"]) for item in records}))
            units = (
                {"angular_velocity": "rad/s", "linear_acceleration": "m/s^2"}
                if type_name == "sensor_msgs/msg/Imu"
                else {"position": "m"}
                if type_name == "geometry_msgs/msg/PoseStamped"
                else {}
            )
            topics.append(
                Topic(topic, type_name, SUPPORTED_TYPES[type_name], frames, units, tuple(records))
            )
        if not topics:
            detail = unsupported[0]["diagnostic"] if unsupported else "no supported messages found"
            raise MCAPValidationError(f"{source}: {detail}")
        epoch = min(message.publish_time_ns for topic in topics for message in topic.messages)
        return MCAPSource(
            source,
            hashlib.sha256(data).hexdigest(),
            profile,
            library,
            tuple(topics),
            tuple(unsupported),
            epoch,
        )
