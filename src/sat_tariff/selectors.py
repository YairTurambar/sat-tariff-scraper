"""Centralized, best-effort selectors adapted from the legacy Selenium scraper."""

from __future__ import annotations

SAT_FORM_NAME = "frmBuscar"
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
SEARCH_BUTTON_TEXTS = ("Consultar", "Buscar")
SECTION_LABELS = {
    "rights": "Derechos e impuestos",
    "nomenclature": "Nomenclatura",
    "restrictions": "Restricciones",
    "quotas": "Cuotas",
}


class SelectorBundle:
    def __init__(self, page):
        self.page = page

    def first_existing(self, selectors: tuple[str, ...]):
        for selector in selectors:
            locator = self.page.locator(selector)
            if locator.count() > 0:
                return locator.first
        return self.page.locator(selectors[0]).first

    def hs_code_input(self):
        return self.first_existing(HS_CODE_INPUT_SELECTORS)

    def captcha_input(self):
        return self.first_existing(CAPTCHA_INPUT_SELECTORS)

    def search_button(self):
        for text in SEARCH_BUTTON_TEXTS:
            locator = self.page.get_by_role("button", name=text)
            if locator.count() > 0:
                return locator.first
            locator = self.page.get_by_role("link", name=text)
            if locator.count() > 0:
                return locator.first
        return self.page.locator("input[type='submit']").first

    def section_trigger(self, label: str):
        role_locator = self.page.get_by_role("button", name=label)
        if role_locator.count() > 0:
            return role_locator.first
        text_locator = self.page.get_by_text(label, exact=True)
        if text_locator.count() > 0:
            return text_locator.first
        return self.page.locator(f"text={label}").first
