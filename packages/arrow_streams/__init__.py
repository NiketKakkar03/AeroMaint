"""Versioned Apache Arrow contracts for dense sensor transport."""

from .schema import SensorField, SensorWindow, encode_sensor_window

__all__ = ["SensorField", "SensorWindow", "encode_sensor_window"]
