import sys
import pytest
from unittest.mock import MagicMock

# Global Test Constants
TEST_APP_ID = "projects/df-reference/locations/us/apps/f39d3ab5-a463-4025-8437-31fd09685d6b"


def pytest_addoption(parser):
    parser.addoption(
        "--run-online",
        action="store_true",
        default=False,
        help="run tests that specifically rely on live API calls",
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "online: mark test as requiring live API access"
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-online"):
        # --run-online given in cli: do not skip online tests
        return
    skip_online = pytest.mark.skip(reason="need --run-online option to run")
    for item in items:
        if "online" in item.keywords:
            item.add_marker(skip_online)


@pytest.fixture
def app_id():
    return TEST_APP_ID


# Create a mock module structure for google.cloud.ces_v1beta
mock_ces = MagicMock()
mock_ces.AgentServiceClient = MagicMock
mock_ces.EvaluationServiceClient = MagicMock
mock_ces.types = MagicMock()
sys.modules["google.cloud.ces_v1beta"] = mock_ces
