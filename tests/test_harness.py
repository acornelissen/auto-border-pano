"""Proves the toolchain itself works before real tests are written."""

from auto_border_pano import __version__
from tests.conftest import synthetic_panorama


def test_package_imports() -> None:
    assert __version__ == "0.2.0"


def test_synthetic_panorama_has_requested_size() -> None:
    img = synthetic_panorama(120, 40)
    assert img.size == (120, 40)
