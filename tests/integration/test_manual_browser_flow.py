import pytest


@pytest.mark.integration
@pytest.mark.manual
def test_manual_browser_flow_placeholder():
    pytest.importorskip("playwright")
    pytest.skip("Live SAT portal access is not exercised in automated test runs.")
