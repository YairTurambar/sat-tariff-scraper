"""SAT tariff scraper with manual CAPTCHA handling and section extraction."""

import logging
import re
import time
from typing import Dict, List, Optional

import pandas as pd
from bs4 import BeautifulSoup
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

PAGE_RELOAD_DELAY = 3
CAPTCHA_TIMEOUT = 300
SECTION_DELAY = 2
DUTIES_TAB_DELAY = 5

SECTION_LABELS = (
    "Derechos e impuestos",
    "Nomenclatura",
    "Restricciones",
    "Cuotas",
)


class SATTariffScraper:
    """Scrape every requested SAT tariff section for each HS code."""

    DUTY_COLUMNS = ("Código", "Descripción", "Código adicional", "Valor")

    def __init__(self, headless=False, manual_captcha=True, captcha_timeout=CAPTCHA_TIMEOUT):
        self.base_url = "https://portal.sat.gob.gt/portal/arancel-integrado/"
        self.consulta_url = (
            "https://farm2.sat.gob.gt/saqbe-arancel-publico"
            "/aduana/arancel/consulta/consulta.jsf"
        )
        self.driver = None
        self.wait = None
        self.results: List[Dict] = []
        self.headless = headless
        self.manual_captcha = manual_captcha
        self.captcha_timeout = captcha_timeout

    def start_browser(self):
        options = webdriver.ChromeOptions()
        if self.headless:
            options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-popup-blocking")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=options)
        self.wait = WebDriverWait(self.driver, 15)
        logger.info("Browser started successfully")

    def navigate_to_portal(self):
        self.driver.get(self.consulta_url)
        time.sleep(PAGE_RELOAD_DELAY)
        self.wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        logger.info("SAT consultation page loaded")

    def find_captcha_field(self):
        selectors = (
            "//input[@id='frmBuscar:txtKaptcha']",
            "//input[contains(@id, 'Kaptcha')]",
            "//input[contains(translate(@id, 'CAPTCHA', 'captcha'), 'captcha')]",
            "//input[contains(translate(@name, 'CAPTCHA', 'captcha'), 'captcha')]",
        )
        for selector in selectors:
            if self.driver.find_elements(By.XPATH, selector):
                return self.driver.find_elements(By.XPATH, selector)[0]
        return None

    def check_for_captcha(self):
        return self.find_captcha_field() is not None

    def handle_captcha_manual(self):
        logger.warning("CAPTCHA detected. Solve it in the visible browser window.")
        logger.warning("The scraper will continue when the CAPTCHA field disappears.")
        deadline = time.time() + self.captcha_timeout
        while time.time() < deadline:
            if not self.check_for_captcha():
                logger.info("CAPTCHA cleared")
                time.sleep(2)
                return True
            time.sleep(1)
        logger.error("CAPTCHA solving timeout")
        return False

    def _find_first(self, selectors, clickable=False):
        def probe(driver):
            for selector in selectors:
                for element in driver.find_elements(By.XPATH, selector):
                    if clickable and not (element.is_displayed() and element.is_enabled()):
                        continue
                    return element
            return False

        try:
            return self.wait.until(probe)
        except TimeoutException:
            return None

    def find_input_field(self):
        return self._find_first((
            "//input[@id='frmBuscar:txtCodigo']",
            "//input[contains(@id, 'txtCodigoArancelario')]",
            "//input[contains(@id, 'txtCodigo')]",
            "//input[contains(@placeholder, 'arancel')]",
            "//input[contains(@class, 'form-control')]",
        ))

    def enter_hs_code(self, hs_code: str):
        field = self.find_input_field()
        if field is None:
            logger.error("HS Code input field not found")
            return False
        field.clear()
        field.send_keys(hs_code)
        return True

    def click_search_button(self):
        button = self._find_first((
            "//input[@id='frmBuscar:pen']",
            "//input[@type='submit' and @value='Buscar']",
            "//input[@type='submit' and contains(@value, 'Consultar')]",
            "//button[contains(@id, 'btnBuscar')]",
            "//button[contains(text(), 'Consultar')]",
            "//button[contains(text(), 'Buscar')]",
            "//button[@type='submit']",
        ), clickable=True)
        if button is None:
            logger.error("Search button not found")
            return False
        button.click()
        time.sleep(3)
        return True

    @staticmethod
    def _direct_rows(table):
        return [row for row in table.find_all("tr") if row.find_parent("table") is table]

    @staticmethod
    def _direct_cells(row):
        return [cell for cell in row.find_all(["td", "th"]) if cell.find_parent("tr") is row]

    @staticmethod
    def _cell_text(cell):
        return cell.get_text(" ", strip=True)

    def _parse_all_tables(self, soup):
        """Preserve every cell from every table, including duplicate labels."""
        data = {}
        for table_number, table in enumerate(soup.find_all("table"), start=1):
            for row_number, row in enumerate(self._direct_rows(table), start=1):
                cells = self._direct_cells(row)
                for column_number, cell in enumerate(cells, start=1):
                    value = self._cell_text(cell)
                    if value:
                        data[f"table_{table_number}_row_{row_number}_col_{column_number}"] = value
                if len(cells) >= 2:
                    key = self._cell_text(cells[0])
                    value = self._cell_text(cells[1])
                    if key and value:
                        # Keep repeated keys instead of overwriting information.
                        base = f"label_{key}"
                        index = 1
                        candidate = base
                        while candidate in data:
                            index += 1
                            candidate = f"{base}_{index}"
                        data[candidate] = value
        return data

    def _parse_leaf_key_values(self, soup):
        data = {}
        for element in soup.find_all(["div", "span", "p", "li"]):
            if element.find(["div", "span", "p", "li", "table"]):
                continue
            text = element.get_text(" ", strip=True)
            if ":" not in text or len(text) > 300:
                continue
            key, value = text.split(":", 1)
            if key.strip() and value.strip():
                base = f"label_{key.strip()}"
                index = 1
                candidate = base
                while candidate in data:
                    index += 1
                    candidate = f"{base}_{index}"
                data[candidate] = value.strip()
        return data

    def _parse_duties(self, soup):
        """Add stable duty columns in addition to the lossless table capture."""
        data = {}
        treatment = "GENERAL"
        for table in soup.find_all("table"):
            rows = self._direct_rows(table)
            texts = [[self._cell_text(cell) for cell in self._direct_cells(row)] for row in rows]
            if not texts or not all(column in texts[0] for column in self.DUTY_COLUMNS):
                continue
            header = texts[0]
            indexes = {name: header.index(name) for name in self.DUTY_COLUMNS}
            for row in texts[1:]:
                if len(row) <= indexes["Valor"]:
                    continue
                code = row[indexes["Código"]]
                if not code or code == "Código":
                    continue
                data[f"{code}_{treatment}"] = row[indexes["Valor"]]
                description = row[indexes["Descripción"]]
                if description:
                    data.setdefault(f"{code}_Descripcion", description)
        return data

    def extract_section_data(self, section_label):
        """Extract all visible information from the currently open section."""
        soup = BeautifulSoup(self.driver.page_source, "html.parser")
        data = self._parse_all_tables(soup)
        data.update(self._parse_leaf_key_values(soup))
        if section_label == "Derechos e impuestos":
            data.update(self._parse_duties(soup))
        return data or {"status": "No data found"}

    _SECTION_JS = """
    var form = document.forms['frmBuscar'];
    if (!form) return 'no form';
    var label = arguments[0], target = arguments[1], marker = arguments[2];
    var inputs = form.getElementsByTagName('input'), button = null;
    for (var i = 0; i < inputs.length; i++) {
      if (inputs[i].type === 'submit' &&
          (inputs[i].value === label || inputs[i].value.indexOf(label) !== -1)) {
        button = inputs[i]; break;
      }
    }
    if (!button) return 'no button';
    window.open('about:blank', target);
    form.target = target;
    var hidden = document.createElement('input');
    hidden.type = 'hidden'; hidden.name = button.name; hidden.value = button.value;
    hidden.id = marker; form.appendChild(hidden); form.submit(); return 'ok';
    """

    _RESTORE_FORM_JS = """
    var form = document.forms['frmBuscar'];
    if (form) { form.target = ''; var marker = document.getElementById(arguments[0]);
      if (marker) marker.parentNode.removeChild(marker); }
    """

    def extract_section_in_new_tab(self, section_label) -> Optional[Dict]:
        """Open one SAT section in a temporary tab without losing the search session."""
        main_handle = self.driver.current_window_handle
        before = set(self.driver.window_handles)
        marker = f"__sat_section_{re.sub(r'[^A-Za-z0-9]', '_', section_label)}"
        target = f"sat_{re.sub(r'[^A-Za-z0-9]', '_', section_label)}"
        try:
            result = self.driver.execute_script(self._SECTION_JS, section_label, target, marker)
            if result != "ok":
                logger.warning("Could not open section %s: %s", section_label, result)
                return None
            time.sleep(DUTIES_TAB_DELAY if section_label == "Derechos e impuestos" else SECTION_DELAY)
            handles = set(self.driver.window_handles) - before
            if not handles:
                logger.warning("Temporary tab did not open for %s", section_label)
                return None
            self.driver.switch_to.window(handles.pop())
            data = self.extract_section_data(section_label)
            self.driver.close()
            return data
        except Exception:
            logger.exception("Error extracting section %s", section_label)
            return None
        finally:
            if main_handle in self.driver.window_handles:
                self.driver.switch_to.window(main_handle)
                self.driver.execute_script(self._RESTORE_FORM_JS, marker)

    @staticmethod
    def _prefix_section_data(section_label, data):
        prefix = re.sub(r"[^A-Za-z0-9]+", "_", section_label).strip("_")
        return {f"{prefix}__{key}": value for key, value in data.items()}

    @staticmethod
    def _safe_sheet_name(name: str) -> str:
        safe_name = re.sub(r"[\[\]:*?/\\]", "_", name).strip()
        return safe_name[:31] or "Sheet"

    @staticmethod
    def _build_section_status(overall_status: str, section_status: str) -> str:
        return section_status if section_status != "Success" else overall_status

    @staticmethod
    def _build_section_row(result: Dict, section_label: str) -> Dict:
        section_statuses = result.get("Section_Statuses", {})
        overall_status = result.get("Status", "")
        row = {
            "HS_Code": result.get("HS_Code", ""),
            "Status": SATTariffScraper._build_section_status(
                overall_status,
                section_statuses.get(section_label, overall_status),
            ),
        }
        section_data = {
            key: value
            for key, value in result.get("Sections", {}).get(section_label, {}).items()
            if key != "status"
        }
        row.update(section_data)
        return row

    @staticmethod
    def _format_worksheet(worksheet):
        border = Border(*(Side(style="thin"),) * 4)
        for column in worksheet.columns:
            letter = column[0].column_letter
            worksheet.column_dimensions[letter].width = min(
                max(len(str(cell.value or "")) for cell in column) + 2, 60
            )
        for cell in worksheet[1]:
            cell.fill = PatternFill("solid", fgColor="4472C4")
            cell.font = Font(bold=True, color="FFFFFF")
            cell.alignment = Alignment(horizontal="center", wrap_text=True)
            cell.border = border
        for row in worksheet.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = Alignment(vertical="top", wrap_text=True)
                cell.border = border

    def scrape_hs_code(self, hs_code: str):
        result = {
            "HS_Code": hs_code,
            "Sections": {section_label: {} for section_label in SECTION_LABELS},
            "Section_Statuses": {section_label: "Not attempted" for section_label in SECTION_LABELS},
        }
        if self.check_for_captcha():
            if not self.manual_captcha or not self.handle_captcha_manual():
                result["Status"] = "CAPTCHA solving failed"
                result["Section_Statuses"] = {
                    section_label: result["Status"] for section_label in SECTION_LABELS
                }
                return result
        if not self.enter_hs_code(hs_code) or not self.click_search_button():
            result["Status"] = "Failed to submit HS code"
            result["Section_Statuses"] = {
                section_label: result["Status"] for section_label in SECTION_LABELS
            }
            return result
        if self.check_for_captcha() and (not self.manual_captcha or not self.handle_captcha_manual()):
            result["Status"] = "CAPTCHA solving failed after search"
            result["Section_Statuses"] = {
                section_label: result["Status"] for section_label in SECTION_LABELS
            }
            return result

        failures = []
        for section_label in SECTION_LABELS:
            logger.info("Extracting %s for HS %s", section_label, hs_code)
            section_data = self.extract_section_in_new_tab(section_label)
            if section_data is None:
                failures.append(section_label)
                result["Section_Statuses"][section_label] = "Section extraction failed"
            else:
                result["Sections"][section_label] = section_data
                section_status = section_data.get("status")
                result["Section_Statuses"][section_label] = section_status or "Success"
        result["Status"] = "Success" if not failures else f"Missing sections: {', '.join(failures)}"
        return result

    def scrape_multiple(self, hs_codes: List[str]):
        self.navigate_to_portal()
        for index, hs_code in enumerate(hs_codes):
            result = self.scrape_hs_code(hs_code)
            self.results.append(result)
            if result["Status"].startswith("CAPTCHA"):
                break
            if index < len(hs_codes) - 1:
                time.sleep(SECTION_DELAY)
        logger.info("Completed scraping %d HS codes", len(self.results))

    def export_to_excel(self, output_file="sat_tariff_data.xlsx"):
        with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
            for section_label in SECTION_LABELS:
                rows = [self._build_section_row(result, section_label) for result in self.results]
                df = pd.DataFrame(rows)
                if df.empty:
                    df = pd.DataFrame(columns=["HS_Code", "Status"])
                ordered_columns = ["HS_Code", "Status"] + [
                    column for column in df.columns if column not in {"HS_Code", "Status"}
                ]
                df = df.reindex(columns=ordered_columns)
                sheet_name = self._safe_sheet_name(section_label)
                df.to_excel(writer, sheet_name=sheet_name, index=False)
                self._format_worksheet(writer.sheets[sheet_name])

    def close_browser(self):
        if self.driver:
            self.driver.quit()

    def run(self, hs_codes: List[str], output_file="sat_tariff_data.xlsx"):
        try:
            self.start_browser()
            self.scrape_multiple(hs_codes)
            self.export_to_excel(output_file)
        finally:
            self.close_browser()


if __name__ == "__main__":
    SATTariffScraper(headless=False, manual_captcha=True).run(["0101210000"])
