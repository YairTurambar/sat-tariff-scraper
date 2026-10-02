"""Centralized, best-effort selectors adapted from the legacy Selenium scraper."""

from __future__ import annotations

SAT_FORM_NAME = "frmBuscar"
SAT_FORM_SELECTOR = "form[name='frmBuscar']"
HS_CODE_INPUT_SELECTORS = (
    "#frmBuscar\\:txtCodigo",
    "input[name='frmBuscar:txtCodigo']",
    "input[placeholder*='arancel' i]",
    "input[id*='txtCodigo']",
)
CAPTCHA_INPUT_SELECTORS = (
    "#frmBuscar\\:txtKaptcha",
    "input[id*='Kaptcha']",
    "input[id*='captcha' i]",
    "input[name*='captcha' i]",
)
SEARCH_BUTTON_SELECTORS = (
    "#frmBuscar\\:pen",
    "input[name='frmBuscar:pen']",
    "input[type='submit'][value='Buscar']",
    "input[type='submit'][value='Consultar']",
    "button[name='frmBuscar:pen']",
)
SEARCH_BUTTON_TEXTS = ("Consultar", "Buscar")
SECTION_LABELS = {
    "rights": "Derechos e impuestos",
    "nomenclature": "Nomenclatura",
    "restrictions": "Restricciones",
    "quotas": "Cuotas",
}


def section_submit_selectors(label: str) -> tuple[str, ...]:
    """Selectors for the JSF submit button that opens a result section."""

    escaped = label.replace("'", "\\'")
    return (
        f"{SAT_FORM_SELECTOR} input[type='submit'][value='{escaped}']",
        f"{SAT_FORM_SELECTOR} input[value='{escaped}']",
        f"input[type='submit'][value='{escaped}']",
        f"{SAT_FORM_SELECTOR} button:has-text('{escaped}')",
    )


def find_form_context(page):
    """Return the ``Page`` or ``Frame`` that owns the ``frmBuscar`` form.

    The direct consulta URL exposes the form on the main document, but a
    configured landing page renders it inside an iframe.
    """

    try:
        if page.locator(SAT_FORM_SELECTOR).count() > 0:
            return page
    except Exception:  # pragma: no cover - defensive, depends on page state
        pass
    for frame in getattr(page, "frames", []) or []:
        if frame is page:
            continue
        try:
            if frame.locator(SAT_FORM_SELECTOR).count() > 0:
                return frame
        except Exception:  # pragma: no cover - detached frames
            continue
    return page


class SelectorBundle:
    def __init__(self, page):
        self.page = page

    def first_existing(self, selectors: tuple[str, ...]):
        for selector in selectors:
            locator = self.page.locator(selector)
            if locator.count() > 0:
                return locator.first
        return self.page.locator(selectors[0]).first

    def has_any(self, selectors: tuple[str, ...]) -> bool:
        for selector in selectors:
            if self.page.locator(selector).count() > 0:
                return True
        return False

    def form(self):
        return self.page.locator(SAT_FORM_SELECTOR).first

    def hs_code_input(self):
        return self.first_existing(HS_CODE_INPUT_SELECTORS)

    def captcha_input(self):
        return self.first_existing(CAPTCHA_INPUT_SELECTORS)

    def search_button(self):
        for selector in SEARCH_BUTTON_SELECTORS:
            locator = self.page.locator(selector)
            if locator.count() > 0:
                return locator.first
        for text in SEARCH_BUTTON_TEXTS:
            locator = self.page.get_by_role("button", name=text)
            if locator.count() > 0:
                return locator.first
            locator = self.page.get_by_role("link", name=text)
            if locator.count() > 0:
                return locator.first
        return self.page.locator("input[type='submit']").first

    def section_trigger(self, label: str):
        for selector in section_submit_selectors(label):
            locator = self.page.locator(selector)
            if locator.count() > 0:
                return locator.first
        role_locator = self.page.get_by_role("button", name=label)
        if role_locator.count() > 0:
            return role_locator.first
        text_locator = self.page.get_by_text(label, exact=True)
        if text_locator.count() > 0:
            return text_locator.first
        return self.page.locator(f"text={label}").first
