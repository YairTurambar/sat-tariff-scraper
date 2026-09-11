"""
SAT Tariff Scraper - Enhanced Version with CAPTCHA Handling
Automated script to extract tariff information from Guatemalan SAT portal
and export to Excel format.
"""

import re
import time
import logging
from typing import List, Dict, Optional
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import pandas as pd
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Seconds to wait after forcing a full reload of the consultation form.
PAGE_RELOAD_DELAY = 3

# Seconds allowed to clear the CAPTCHA gate. The portal re-arms it for every blank
# search form, but the duties view is rendered in a throwaway tab so the validated
# results page survives - in practice this is hit once per run.
CAPTCHA_TIMEOUT = 300

# Button label that opens the duties/taxes view. Matched on the label because the
# JSF id (frmBuscar:_idJsp82) is auto-generated and shifts with the page layout.
DERECHOS_LABEL = "Derechos e impuestos"

# Seconds to let the duties tab finish loading before reading it.
DUTIES_TAB_DELAY = 5


class SATTariffScraper:
    """Scraper for SAT tariff information with CAPTCHA handling"""

    # Column headers of the duties/taxes grid repeated for every trade agreement.
    DUTY_COLUMNS = ("Código", "Descripción", "Código adicional", "Valor")

    def __init__(self, headless=False, manual_captcha=True, captcha_timeout=CAPTCHA_TIMEOUT):
        """
        Initialize the scraper with Selenium WebDriver
        
        Args:
            headless: Whether to run browser in headless mode
            manual_captcha: If True, pauses for manual CAPTCHA entry (recommended)
            captcha_timeout: Seconds to wait for the CAPTCHA gate to be cleared
        """
        self.base_url = "https://portal.sat.gob.gt/portal/arancel-integrado/"
        # base_url only hosts the public landing page; the real SAQB'E consultation
        # form lives in a nested iframe served from a different host, so drive it
        # directly instead of fighting two levels of frame switching.
        self.consulta_url = (
            "https://farm2.sat.gob.gt/saqbe-arancel-publico"
            "/aduana/arancel/consulta/consulta.jsf"
        )
        self.driver = None
        self.wait = None
        self.results = []
        self.headless = headless
        self.manual_captcha = manual_captcha
        self.captcha_timeout = captcha_timeout

    def start_browser(self):
        """Start Chrome browser with Selenium"""
        try:
            options = webdriver.ChromeOptions()
            
            if self.headless:
                options.add_argument('--headless')
            
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-blink-features=AutomationControlled')
            # The duties view is opened in a second tab so the results page (and
            # with it the validated session) survives; without this Chrome treats
            # that as a popup and blocks it.
            options.add_argument('--disable-popup-blocking')
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option('useAutomationExtension', False)
            
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=options)
            self.wait = WebDriverWait(self.driver, 15)
            logger.info("Browser started successfully")
        except Exception as e:
            logger.error(f"Error starting browser: {e}")
            raise

    def navigate_to_portal(self):
        """Navigate to SAT portal consultation page"""
        try:
            logger.info(f"Navigating to SAT portal consultation page...")
            self.driver.get(self.consulta_url)
            time.sleep(3)
            
            # Wait for page to load
            self.wait.until(EC.presence_of_all_elements_located((By.TAG_NAME, "body")))
            logger.info("Portal loaded successfully")
            
        except Exception as e:
            logger.error(f"Error navigating to portal: {e}")
            raise

    def handle_captcha_manual(self):
        """
        Pause and wait for the CAPTCHA gate to be cleared by the user.

        The gate guards the session rather than each query, so this normally
        needs to happen once per run.
        """
        try:
            minutes = self.captcha_timeout / 60
            logger.warning("\n" + "="*60)
            logger.warning("⚠️  CAPTCHA DETECTED - Manual intervention required")
            logger.warning("="*60)
            logger.warning("Please complete the CAPTCHA in the browser window:")
            logger.warning("1. A browser window is open with the SAT portal")
            logger.warning("2. Look for the CAPTCHA field")
            logger.warning("3. Solve the CAPTCHA and click search")
            logger.warning("4. The script will automatically continue after solving")
            logger.warning(f"You have {minutes:.0f} minute(s); this is normally asked once per run.")
            logger.warning("="*60 + "\n")

            start_time = time.time()

            while time.time() - start_time < self.captcha_timeout:
                # The gate is cleared once the CAPTCHA field is gone from the page.
                # Waiting for a results table instead would miss the common case
                # where solving the CAPTCHA only reveals the HS Code search form.
                if not self.check_for_captcha():
                    logger.info("✅ CAPTCHA solved! Continuing with data extraction...")
                    time.sleep(2)
                    return True
                time.sleep(1)

            logger.error(f"❌ CAPTCHA solving timeout - exceeded {minutes:.0f} minute(s)")
            return False

        except Exception as e:
            logger.error(f"Error in manual CAPTCHA handling: {e}")
            return False

    def find_captcha_field(self):
        """Locate the CAPTCHA input field"""
        try:
            selectors = [
                "//input[@id='frmBuscar:txtKaptcha']",
                "//input[contains(@id, 'Kaptcha')]",
                "//input[contains(@id, 'captcha')]",
                "//input[contains(@name, 'captcha')]",
            ]
            
            for selector in selectors:
                try:
                    field = self.driver.find_element(By.XPATH, selector)
                    logger.debug(f"Found CAPTCHA field with selector: {selector}")
                    return field
                except:
                    continue
            
            return None
            
        except Exception as e:
            logger.error(f"Error finding CAPTCHA field: {e}")
            return None

    def check_for_captcha(self):
        """Check if CAPTCHA is present on the page"""
        try:
            captcha_field = self.find_captcha_field()
            if captcha_field:
                logger.warning("CAPTCHA detected on page")
                return True
            return False
        except:
            return False

    def _find_first(self, selectors, clickable=False):
        """
        Return the first element matching any selector.

        Probes every selector inside a single wait; waiting per selector would
        multiply the timeout by the number of candidates whenever none match.
        """
        def _probe(driver):
            for selector in selectors:
                for match in driver.find_elements(By.XPATH, selector):
                    if clickable and not (match.is_displayed() and match.is_enabled()):
                        continue
                    logger.debug(f"Matched selector: {selector}")
                    return match
            return False

        try:
            return self.wait.until(_probe)
        except TimeoutException:
            return None

    def find_input_field(self):
        """Locate the HS Code input field"""
        try:
            logger.info("Searching for HS Code input field...")

            # The SAQB'E form labels this field "Posición arancelaria".
            selectors = [
                "//input[@id='frmBuscar:txtCodigo']",
                "//input[contains(@id, 'txtCodigoArancelario')]",
                "//input[contains(@id, 'txtCodigo')]",
                "//input[contains(@placeholder, 'arancel')]",
                "//input[contains(@class, 'form-control')]",
            ]

            field = self._find_first(selectors)
            if field is None:
                logger.warning("Could not locate input field with predefined selectors")
                return None

            logger.info("Found HS Code input field")
            return field

        except Exception as e:
            logger.error(f"Error finding input field: {e}")
            return None

    def enter_hs_code(self, hs_code: str) -> bool:
        """Enter HS Code in the input field"""
        try:
            logger.info(f"Entering HS Code: {hs_code}")
            
            input_field = self.find_input_field()
            if not input_field:
                logger.error("Input field not found")
                return False
            
            input_field.clear()
            input_field.send_keys(hs_code)
            logger.info(f"HS Code {hs_code} entered successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error entering HS Code: {e}")
            return False

    def click_search_button(self) -> bool:
        """Click the search/consult button"""
        try:
            logger.info("Looking for search button...")

            # SAQB'E renders the search control as <input type="submit" value="Buscar">,
            # not a <button>, so match inputs first.
            selectors = [
                "//input[@id='frmBuscar:pen']",
                "//input[@type='submit' and @value='Buscar']",
                "//input[@type='submit' and contains(@value, 'Consultar')]",
                "//button[contains(@id, 'btnBuscar')]",
                "//button[contains(text(), 'Consultar')]",
                "//button[contains(text(), 'Buscar')]",
                "//button[@type='submit']",
            ]

            button = self._find_first(selectors, clickable=True)
            if button is None:
                logger.warning("Could not find search button")
                return False

            button.click()
            logger.info("Search button clicked")
            time.sleep(3)
            return True

        except Exception as e:
            logger.error(f"Error clicking search button: {e}")
            return False

    def extract_tariff_data(self) -> Dict:
        """Extract all tariff information from the results page"""
        try:
            logger.info("Extracting tariff data...")
            time.sleep(2)
            
            # Get page HTML
            html = self.driver.page_source
            soup = BeautifulSoup(html, 'html.parser')
            
            # Extract data based on common table/div structures
            data = self._parse_tariff_table(soup)
            
            logger.info("Tariff data extracted successfully")
            return data
            
        except Exception as e:
            logger.error(f"Error extracting tariff data: {e}")
            return {}

    def _parse_tariff_table(self, soup) -> Dict:
        """Parse the tariff information from HTML"""
        try:
            tables = soup.find_all('table')

            data = {}
            data.update(self._parse_classification(tables))
            data.update(self._parse_duties(tables))

            if not data:
                data.update(self._parse_key_values(soup))

            return data if data else {"status": "No data found"}

        except Exception as e:
            logger.error(f"Error parsing tariff table: {e}")
            return {}

    @staticmethod
    def _direct_rows(table):
        """
        Rows owned by this table.

        SAQB'E nests tables many levels deep, so find_all('tr') alone would
        attribute a descendant's rows to every ancestor table and collapse whole
        pages into single keys.
        """
        return [r for r in table.find_all('tr') if r.find_parent('table') is table]

    @staticmethod
    def _direct_cells(row):
        """Cells owned by this row rather than by a table nested inside it."""
        return [c for c in row.find_all(['td', 'th']) if c.find_parent('tr') is row]

    @staticmethod
    def _cell_text(cell) -> str:
        return cell.get_text(" ", strip=True)

    @staticmethod
    def _treatment_label(title: str) -> str:
        """
        Condense a treatment heading into a short, Excel-friendly suffix.

        'Tratado de Libre Comercio ... - MX' -> 'MX'
        'TRATAMIENTO GENERAL'                -> 'GENERAL'
        """
        tail = title.rsplit(" - ", 1)[-1].strip()
        if tail and len(tail) <= 6:
            return tail
        return title.replace("TRATAMIENTO", "").strip()[:40] or "GENERAL"

    def _parse_classification(self, tables) -> Dict:
        """Pull section/chapter/heading details out of the results panel"""
        data = {}
        hierarchy = {}
        code_pattern = re.compile(r"^\d{4}(\.\d+)*$")

        for table in tables:
            for row in self._direct_rows(table):
                cells = self._direct_cells(row)
                if len(cells) < 2 or any(c.find('table') for c in cells[:2]):
                    continue

                key = self._cell_text(cells[0])
                value = self._cell_text(cells[1])
                if not key or not value:
                    continue

                if key.startswith("Sección"):
                    data["Seccion"] = key.split("Sección", 1)[1].strip()
                    data["Seccion_Descripcion"] = value
                elif key.startswith("Capítulo"):
                    data["Capitulo"] = key.split(":")[-1].strip()
                    data["Capitulo_Descripcion"] = value
                elif code_pattern.match(key):
                    hierarchy[key] = value

        if hierarchy:
            # The longest code is the most specific one, i.e. the queried inciso.
            inciso = max(hierarchy, key=len)
            partida = min(hierarchy, key=len)
            data["Inciso"] = inciso
            data["Descripcion"] = hierarchy[inciso]
            data["Partida"] = partida
            data["Partida_Descripcion"] = hierarchy[partida]

        return data

    def _parse_duties(self, tables) -> Dict:
        """Parse the 'Derechos e impuestos' grids into flat columns"""
        data = {}
        treatment = "GENERAL"

        for table in tables:
            rows = self._direct_rows(table)
            if not rows:
                continue

            texts = [[self._cell_text(c) for c in self._direct_cells(r)] for r in rows]

            # A standalone one-cell table introduces the trade agreement that the
            # duty grid immediately below it belongs to. Cells wrapping a nested
            # table are layout containers, not headings.
            if len(texts) == 1:
                if any(c.find('table') for c in self._direct_cells(rows[0])):
                    continue
                labels = [t for t in texts[0] if t]
                if len(labels) == 1 and not labels[0].startswith("Resultados"):
                    treatment = self._treatment_label(labels[0])
                continue

            header = texts[0]
            if not all(column in header for column in self.DUTY_COLUMNS):
                continue

            index = {name: header.index(name) for name in self.DUTY_COLUMNS}
            for cells in texts[1:]:
                if len(cells) <= index["Valor"]:
                    continue

                code = cells[index["Código"]]
                value = cells[index["Valor"]]
                if not code or code == "Código":
                    continue

                data[f"{code}_{treatment}"] = value
                description = cells[index["Descripción"]]
                if description:
                    data.setdefault(f"{code}_Descripcion", description)

        return data

    def _parse_key_values(self, soup) -> Dict:
        """Fallback for layouts that do not match the known SAQB'E grids"""
        data = {}
        for div in soup.find_all('div'):
            if div.find('div') or div.find('table'):
                continue
            text = div.get_text(" ", strip=True)
            if ':' in text and len(text) < 200:
                key, value = text.split(':', 1)
                if key.strip() and value.strip():
                    data[key.strip()] = value.strip()
        return data

    def click_derechos_e_impuestos(self) -> bool:
        """Click on 'Derechos e impuestos' tab/button"""
        try:
            logger.info("Looking for 'Derechos e impuestos' tab...")

            # SAQB'E renders this as <input type="submit" value="Derechos e impuestos">.
            # Match on @value rather than the auto-generated JSF id (_idJsp82),
            # which shifts whenever the page layout changes.
            selectors = [
                f"//input[@type='submit' and @value='{DERECHOS_LABEL}']",
                "//input[@type='submit' and contains(@value, 'Derechos')]",
                "//a[contains(@id, 'Derechos')]",
                "//button[contains(text(), 'Derechos')]",
                "//a[contains(text(), 'Derechos')]",
                "//span[contains(text(), 'Derechos')]",
                "//li[@role='tab']//a[contains(text(), 'Derechos')]",
            ]

            element = self._find_first(selectors, clickable=True)
            if element is None:
                logger.warning("Could not find 'Derechos e impuestos' tab")
                return False

            element.click()
            logger.info("Clicked on 'Derechos e impuestos'")
            time.sleep(2)
            return True

        except Exception as e:
            logger.error(f"Error clicking 'Derechos e impuestos': {e}")
            return False

    # Submits frmBuscar into a named second tab. Clicking the button lets the
    # page's own handler reset form.target, which replaces the results page;
    # form.submit() skips onclick handlers and honours the target instead.
    _DUTIES_IN_TAB_JS = """
    var f = document.forms['frmBuscar'];
    if (!f) { return 'no form'; }
    var btn = null, ins = f.getElementsByTagName('input');
    for (var i = 0; i < ins.length; i++) {
        if (ins[i].type === 'submit' && ins[i].value === arguments[0]) { btn = ins[i]; break; }
    }
    if (!btn) { return 'no button'; }
    window.open('about:blank', arguments[1]);
    f.target = arguments[1];
    var h = document.createElement('input');
    h.type = 'hidden';
    h.name = btn.name;
    h.value = btn.value;
    h.id = arguments[2];
    f.appendChild(h);
    f.submit();
    return 'ok';
    """

    _RESTORE_FORM_JS = """
    var f = document.forms['frmBuscar'];
    if (f) {
        f.target = '';
        var h = document.getElementById(arguments[0]);
        if (h) { h.parentNode.removeChild(h); }
    }
    """

    def extract_duties_in_new_tab(self) -> Optional[Dict]:
        """
        Open 'Derechos e impuestos' in a second tab and extract the duty data there.

        The portal re-arms the CAPTCHA whenever a *blank* search form is loaded,
        but the results page keeps frmBuscar:txtCodigo and lets you search again
        without one. Navigating to the duties view in place destroys that page and
        therefore costs a CAPTCHA per code; rendering it in a throwaway tab leaves
        the validated session intact, so the run needs a single solve.
        """
        driver = self.driver
        main_handle = driver.current_window_handle
        before = set(driver.window_handles)
        tab_name = "satDutiesTab"
        trigger_id = "__sat_duties_trigger"

        try:
            logger.info("Opening 'Derechos e impuestos' in a second tab...")
            result = driver.execute_script(
                self._DUTIES_IN_TAB_JS, DERECHOS_LABEL, tab_name, trigger_id
            )
            if result != "ok":
                logger.warning(f"Could not submit duties form: {result}")
                return None

            time.sleep(DUTIES_TAB_DELAY)
            new_handles = set(driver.window_handles) - before
            if not new_handles:
                logger.warning("Duties tab did not open")
                return None

            driver.switch_to.window(new_handles.pop())
            time.sleep(2)
            data = self.extract_tariff_data()
            driver.close()
            return data

        except Exception as e:
            logger.error(f"Error extracting duties in new tab: {e}")
            return None

        finally:
            # Always get back to the results tab and undo the temporary submit
            # wiring, otherwise the next 'Buscar' would submit into the dead tab.
            try:
                if main_handle in driver.window_handles:
                    driver.switch_to.window(main_handle)
                    driver.execute_script(self._RESTORE_FORM_JS, trigger_id)
            except Exception as e:
                logger.error(f"Error restoring search form: {e}")

    def scrape_hs_code(self, hs_code: str) -> Dict:
        """Complete scraping process for a single HS Code"""
        try:
            logger.info(f"Starting scrape for HS Code: {hs_code}")
            
            # Check for CAPTCHA
            if self.check_for_captcha():
                if self.manual_captcha:
                    if not self.handle_captcha_manual():
                        return {"HS_Code": hs_code, "Status": "CAPTCHA solving failed"}
                else:
                    logger.error("CAPTCHA encountered but manual_captcha is disabled")
                    return {"HS_Code": hs_code, "Status": "CAPTCHA encountered"}
            
            # Navigate and enter HS Code
            if not self.enter_hs_code(hs_code):
                return {"HS_Code": hs_code, "Status": "Failed to enter HS Code"}
            
            # Click search button
            if not self.click_search_button():
                return {"HS_Code": hs_code, "Status": "Failed to click search"}
            
            # Check for CAPTCHA after search attempt
            if self.check_for_captcha():
                if self.manual_captcha:
                    if not self.handle_captcha_manual():
                        return {"HS_Code": hs_code, "Status": "CAPTCHA solving failed after search"}
            
            # The duties view is opened in a second tab so the results page - and
            # with it the CAPTCHA-validated session - survives for the next code.
            data = self.extract_duties_in_new_tab()
            if data is None:
                return {"HS_Code": hs_code, "Status": "Failed to open duties view"}

            data["HS_Code"] = hs_code
            data["Status"] = "Success"
            
            logger.info(f"Successfully scraped HS Code: {hs_code}")
            return data
            
        except Exception as e:
            logger.error(f"Error scraping HS Code {hs_code}: {e}")
            return {"HS_Code": hs_code, "Status": f"Error: {str(e)}"}

    def return_to_search(self) -> bool:
        """
        Recover the search form when it is no longer on the page.

        Normal runs never need this: the duties view is rendered in a throwaway
        tab, so the results page - which keeps frmBuscar:txtCodigo and accepts a
        new search without a CAPTCHA - is still there for the next code. This is
        only a fallback for when something knocked the browser off that page, and
        it costs a CAPTCHA because the portal re-arms the gate for a blank form.
        """
        try:
            if self.driver.find_elements(By.ID, "frmBuscar:txtCodigo"):
                return True

            logger.warning("Search form lost; reloading it (this needs a new CAPTCHA)")
            self.driver.get(self.consulta_url)
            time.sleep(PAGE_RELOAD_DELAY)
            return True

        except Exception as e:
            logger.error(f"Error returning to search form: {e}")
            return False

    def scrape_multiple(self, hs_codes: List[str]):
        """Scrape multiple HS Codes"""
        try:
            self.navigate_to_portal()

            for position, hs_code in enumerate(hs_codes):
                data = self.scrape_hs_code(hs_code)
                self.results.append(data)

                # The CAPTCHA gate guards the whole session, so if it was not
                # cleared every remaining code would just repeat the same full
                # manual timeout. Stop instead of burning it once per code.
                if str(data.get("Status", "")).startswith("CAPTCHA"):
                    logger.error(
                        "Aborting run: CAPTCHA gate was not cleared, "
                        f"{len(hs_codes) - len(self.results)} code(s) skipped."
                    )
                    break

                if position < len(hs_codes) - 1:
                    self.return_to_search()
                    time.sleep(2)  # Delay between requests

            logger.info(f"Completed scraping {len(self.results)} HS Codes")

        except Exception as e:
            logger.error(f"Error in scrape_multiple: {e}")

    def export_to_excel(self, output_file: str = "sat_tariff_data.xlsx"):
        """Export scraped data to Excel file"""
        try:
            logger.info(f"Exporting data to {output_file}...")
            
            # Convert results to DataFrame
            df = pd.DataFrame(self.results)
            
            # Create Excel file with formatting
            with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Tariff Data', index=False)
                
                # Format the Excel file
                workbook = writer.book
                worksheet = writer.sheets['Tariff Data']
                
                # Set column widths
                for column in worksheet.columns:
                    max_length = 0
                    column_letter = column[0].column_letter
                    for cell in column:
                        try:
                            if len(str(cell.value)) > max_length:
                                max_length = len(str(cell.value))
                        except:
                            pass
                    adjusted_width = min(max_length + 2, 50)
                    worksheet.column_dimensions[column_letter].width = adjusted_width
                
                # Format header row
                header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
                header_font = Font(bold=True, color="FFFFFF")
                border = Border(
                    left=Side(style='thin'),
                    right=Side(style='thin'),
                    top=Side(style='thin'),
                    bottom=Side(style='thin')
                )
                
                for cell in worksheet[1]:
                    cell.fill = header_fill
                    cell.font = header_font
                    cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
                    cell.border = border
                
                # Format data rows
                for row in worksheet.iter_rows(min_row=2, max_row=worksheet.max_row):
                    for cell in row:
                        cell.border = border
                        cell.alignment = Alignment(horizontal='left', vertical='top', wrap_text=True)
            
            logger.info(f"Data successfully exported to {output_file}")
            
        except Exception as e:
            logger.error(f"Error exporting to Excel: {e}")
            raise

    def close_browser(self):
        """Close the browser"""
        if self.driver:
            self.driver.quit()
            logger.info("Browser closed")

    def run(self, hs_codes: List[str], output_file: str = "sat_tariff_data.xlsx"):
        """Run the complete scraping process"""
        try:
            self.start_browser()
            self.scrape_multiple(hs_codes)
            self.export_to_excel(output_file)
            logger.info("Scraping process completed successfully")
        except Exception as e:
            logger.error(f"Fatal error during scraping: {e}")
        finally:
            self.close_browser()


if __name__ == "__main__":
    # Example usage with manual CAPTCHA handling
    hs_codes = ["0101210000"]  # Replace with your HS codes
    
    # headless=False keeps browser window visible for CAPTCHA solving
    # manual_captcha=True enables automatic CAPTCHA detection and waiting
    scraper = SATTariffScraper(headless=False, manual_captcha=True)
    scraper.run(hs_codes)
