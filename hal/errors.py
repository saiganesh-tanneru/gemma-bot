"""Errors raised by hardware drivers and the in-memory mocks."""


class HalError(Exception):
    """Base class for hardware-abstraction failures."""


class UnsupportedAxisError(HalError):
    """The requested head axis is not on this hardware."""

    def __init__(self, axis: str):
        self.axis = axis
        super().__init__(f"Head axis {axis!r} is not available on this hardware")


class UnsupportedOperationError(HalError):
    """The driver cannot perform this operation (for example setting the host clock)."""
