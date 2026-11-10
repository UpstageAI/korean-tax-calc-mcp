"""pytest 공용 픽스처 — call(tool, args) -> dict. 함수로 쓰려면 from tests._helpers import call."""
import pytest

from tests._helpers import call as _call


@pytest.fixture
def call():
    return _call
