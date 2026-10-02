import pytest


@pytest.mark.integration
@pytest.mark.manual
def test_manual_browser_flow_placeholder():
    pytest.importorskip("playwright")
    pytest.skip("Live SAT portal access is not exercised in automated test runs.")


@pytest.mark.integration
@pytest.mark.manual
def test_manual_captcha_then_automatic_extraction():
    """Manual checklist, never executed by default and never solving a CAPTCHA.

    1. Run ``python -m sat_tariff run`` on an interactive desktop.
    2. Solve and submit the CAPTCHA in the browser only; do not press Enter.
    3. The console must print the automatic resumption message and process every
       unique code of ``HS_codes.txt`` without returning to the landing page.
    """

    pytest.importorskip("playwright")
    pytest.skip("Requires an interactive desktop and a human solving the CAPTCHA.")
