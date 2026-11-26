"""GemaBot hardware abstraction layer.

Import this package from tests and from the controller. Board drivers implement
the classes in hal.interfaces and are assembled into a Hardware bundle.
"""

from hal.bundle import Hardware
from hal.errors import HalError, UnsupportedAxisError, UnsupportedOperationError
from hal.face_target import FaceDrawTarget
from hal.mock import build_mock_hardware
from hal.webots import build_webots_hardware

__all__ = [
    "FaceDrawTarget",
    "HalError",
    "Hardware",
    "UnsupportedAxisError",
    "UnsupportedOperationError",
    "build_mock_hardware",
    "build_webots_hardware",
]
