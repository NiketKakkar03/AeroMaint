"""Generate the tiny deterministic ROS 2 MCAP fixture used by contract tests."""

from __future__ import annotations

import hashlib
import struct
from pathlib import Path

MAGIC = b"\x89MCAP0\r\n"
EPOCH = 1_700_000_000_000_000_000


def _string(value: str) -> bytes:
    encoded = value.encode()
    return struct.pack("<I", len(encoded)) + encoded


def _blob(value: bytes) -> bytes:
    return struct.pack("<I", len(value)) + value


def _record(opcode: int, body: bytes) -> bytes:
    return bytes([opcode]) + struct.pack("<Q", len(body)) + body


class CDR:
    def __init__(self) -> None:
        self.value = bytearray(b"\x00\x01\x00\x00")

    def align(self, size: int) -> None:
        self.value.extend(b"\0" * ((-len(self.value)) % size))

    def pack(self, fmt: str, value: object, alignment: int) -> None:
        self.align(alignment)
        self.value.extend(struct.pack("<" + fmt, value))

    def u8(self, value: int) -> None:
        self.pack("B", value, 1)

    def u32(self, value: int) -> None:
        self.pack("I", value, 4)

    def i32(self, value: int) -> None:
        self.pack("i", value, 4)

    def f64(self, value: float) -> None:
        self.pack("d", value, 8)

    def string(self, value: str) -> None:
        encoded = value.encode() + b"\0"
        self.u32(len(encoded))
        self.value.extend(encoded)

    def bytes(self, value: bytes) -> None:
        self.u32(len(value))
        self.value.extend(value)


def _header(cdr: CDR, timestamp: int, frame_id: str) -> None:
    cdr.i32(timestamp // 1_000_000_000)
    cdr.u32(timestamp % 1_000_000_000)
    cdr.string(frame_id)


def _image(timestamp: int) -> bytes:
    cdr = CDR()
    _header(cdr, timestamp, "camera_left_optical")
    cdr.u32(2)
    cdr.u32(2)
    cdr.string("mono8")
    cdr.u8(0)
    cdr.u32(2)
    cdr.bytes(b"\x10\x20\x30\x40")
    return bytes(cdr.value)


def _imu(timestamp: int) -> bytes:
    cdr = CDR()
    _header(cdr, timestamp, "imu_link")
    for value in (0.0, 0.0, 0.0, 1.0):
        cdr.f64(value)
    for value in [0.0] * 9 + [0.1, 0.2, 0.3] + [0.0] * 9 + [0.0, 0.0, 9.81] + [0.0] * 9:
        cdr.f64(value)
    return bytes(cdr.value)


def _pose(timestamp: int) -> bytes:
    cdr = CDR()
    _header(cdr, timestamp, "map")
    for value in (1.0, 2.0, 3.0, 0.0, 0.0, 0.0, 1.0):
        cdr.f64(value)
    return bytes(cdr.value)


def _event(timestamp: int) -> bytes:
    cdr = CDR()
    _header(cdr, timestamp, "airframe")
    cdr.string("warning")
    cdr.string("synthetic vibration threshold")
    return bytes(cdr.value)


SCHEMAS = (
    (
        1,
        "sensor_msgs/msg/Image",
        "std_msgs/Header header\n"
        "uint32 height\nuint32 width\nstring encoding\n"
        "uint8 is_bigendian\nuint32 step\nuint8[] data\n",
    ),
    (
        2,
        "sensor_msgs/msg/Imu",
        "std_msgs/Header header\ngeometry_msgs/Quaternion orientation\n"
        "float64[9] orientation_covariance\ngeometry_msgs/Vector3 angular_velocity\n"
        "float64[9] angular_velocity_covariance\n"
        "geometry_msgs/Vector3 linear_acceleration\n"
        "float64[9] linear_acceleration_covariance\n",
    ),
    (3, "geometry_msgs/msg/PoseStamped", "std_msgs/Header header\ngeometry_msgs/Pose pose\n"),
    (4, "aeromaint_msgs/msg/Event", "std_msgs/Header header\nstring severity\nstring message\n"),
    (5, "std_msgs/msg/String", "string data\n"),
)
CHANNELS = (
    (1, 1, "/camera/left/image_raw"),
    (2, 2, "/imu/data"),
    (3, 3, "/localization/pose"),
    (4, 4, "/maintenance/events"),
    (5, 5, "/debug/text"),
)


def build_mcap(*, supported: bool = True) -> bytes:
    records = [_record(0x01, _string("ros2") + _string("aeromaint-fixture/1.0"))]
    schemas = SCHEMAS if supported else SCHEMAS[-1:]
    channels = CHANNELS if supported else CHANNELS[-1:]
    for schema_id, name, definition in schemas:
        records.append(
            _record(
                0x03,
                struct.pack("<H", schema_id)
                + _string(name)
                + _string("ros2msg")
                + _blob(definition.encode()),
            )
        )
    for channel_id, schema_id, topic in channels:
        records.append(
            _record(
                0x04,
                struct.pack("<HH", channel_id, schema_id)
                + _string(topic)
                + _string("cdr")
                + struct.pack("<I", 0),
            )
        )
    if supported:
        payloads = (
            _image(EPOCH),
            _imu(EPOCH + 10_000_000),
            _pose(EPOCH + 20_000_000),
            _event(EPOCH + 30_000_000),
        )
        for sequence, ((channel_id, _, _), payload) in enumerate(
            zip(CHANNELS[:4], payloads, strict=True), start=1
        ):
            timestamp = EPOCH + (sequence - 1) * 10_000_000
            body = (
                struct.pack("<HIQQ", channel_id, sequence, timestamp + 1_000, timestamp) + payload
            )
            records.append(_record(0x05, body))
    records.append(_record(0x0F, struct.pack("<I", 0)))
    records.append(_record(0x02, struct.pack("<QQI", 0, 0, 0)))
    return MAGIC + b"".join(records) + MAGIC


def main() -> None:
    root = Path("tests/media-fixtures/mcap-mini")
    fixture = root / "ros2-mini.mcap"
    fixture.write_bytes(build_mcap())
    files = [root / "README.md", fixture]
    lines = [f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}" for path in files]
    (root / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
