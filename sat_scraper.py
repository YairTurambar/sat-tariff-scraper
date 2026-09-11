"""
SAT Tariff Scraper - Enhanced Version with CAPTCHA Handling
Automated script to extract tariff information from Guatemalan SAT portal
and export to Excel format.
"""

import time
import logging
from typing import List, Dict
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
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


class SATTariffScraper:
    """Scraper for SAT tariff information with CAPTCHA handling"""

    def __init__(self, headless=False, manual_captcha=True):
        """
        Initialize the scraper with Selenium WebDriver
        
        Args:
            headless: Whether to run browser in headless mode
            manual_captcha: If True, pauses for manual CAPTCHA entry (recommended)
        """
        self.base_url = "https://portal.sat.gob.gt/portal/arancel-integrado/"
        self.consulta_url = "https://portal.sat.gob.gt/portal/consulta.jsf"
        self.driver = None
        self.wait = None
        self.results = []
        self.headless = headless
        self.manual_captcha = manual_captcha

    def start_browser(self):
        """Start Chrome browser with Selenium"""
        try:
            options = webdriver.ChromeOptions()
            
            if self.headless:
                options.add_argument('--headless')
            
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-blink-features=AutomationControlled')
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
        Pause and wait for manual CAPTCHA entry by user
        This is the most reliable method for dealing with CAPTCHA
        """
        try:
            logger.warning("\n" + "="*60)
            logger.warning("⚠️  CAPTCHA DETECTED - Manual intervention required")
            logger.warning("="*60)
            logger.warning("Please complete the CAPTCHA in the browser window:")
            logger.warning("1. A browser window is open with the SAT portal")
            logger.warning("2. Look for the CAPTCHA field")
            logger.warning("3. Solve the CAPTCHA and click search")
            logger.warning("4. The script will automatically continue after solving")
            logger.warning("="*60 + "\n")
            
            # Wait for user to complete CAPTCHA by looking for search results
            # or for a specific element that appears after CAPTCHA is solved
            max_wait_time = 120  # 2 minutes to solve CAPTCHA
            start_time = time.time()
            
            while time.time() - start_time < max_wait_time:
                try:
                    # Check if results table or data appears
                    # This indicates CAPTCHA was solved
                    self.driver.find_element(By.XPATH, "//table//tr[position() > 1]")
                    logger.info("✅ CAPTCHA solved! Continuing with data extraction...")
                    time.sleep(2)
                    return True
                except:
                    time.sleep(1)
                    continue
            
            logger.error("❌ CAPTCHA solving timeout - exceeded 2 minutes")
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

    def find_input_field(self):
        """Locate the HS Code input field"""
        try:
            logger.info("Searching for HS Code input field...")
            
            selectors = [
                "//input[@id='frmBuscar:txtCodigoArancelario']",
                "//input[contains(@id, 'txtCodigoArancelario')]",
                "//input[@placeholder*='HS']",
                "//input[@name*='hs']",
                "//input[@placeholder*='arancel']",
                "//input[@placeholder*='Código']",
                "//input[contains(@class, 'form-control')]",
            ]
            
            for selector in selectors:
                try:
                    field = self.wait.until(EC.presence_of_element_located((By.XPATH, selector)))
                    logger.info(f"Found input field with selector: {selector}")
                    return field
                except:
                    continue
            
            logger.warning("Could not locate input field with predefined selectors")
            return None
            
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
            
            selectors = [
                "//button[contains(@id, 'btnBuscar')]",
                "//button[contains(text(), 'Consultar')]",
                "//button[contains(text(), 'Buscar')]",
                "//button[@type='submit']",
                "//input[@type='submit' and contains(@value, 'Consultar')]",
                "//button[contains(@class, 'btn-primary')]",
            ]
            
            for selector in selectors:
                try:
                    button = self.wait.until(EC.element_to_be_clickable((By.XPATH, selector)))
                    button.click()
                    logger.info("Search button clicked")
                    time.sleep(3)
                    return True
                except:
                    continue
            
            logger.warning("Could not find search button")
            return False
            
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
            data = {}
            
            # Try to find tables
            tables = soup.find_all('table')
            if tables:
                for table in tables:
                    rows = table.find_all('tr')
                    for row in rows:
                        cols = row.find_all(['td', 'th'])
                        if len(cols) >= 2:
                            key = cols[0].get_text(strip=True)
                            value = cols[1].get_text(strip=True)
                            if key:
                                data[key] = value
            
            # Try to find divs with key-value pairs
            if not data:
                divs = soup.find_all('div')
                for div in divs:
                    text = div.get_text(strip=True)
                    if ':' in text:
                        parts = text.split(':', 1)
                        if len(parts) == 2:
                            data[parts[0].strip()] = parts[1].strip()
            
            return data if data else {"status": "No data found"}
            
        except Exception as e:
            logger.error(f"Error parsing tariff table: {e}")
            return {}

    def click_derechos_e_impuestos(self) -> bool:
        """Click on 'Derechos e impuestos' tab/button"""
        try:
            logger.info("Looking for 'Derechos e impuestos' tab...")
            
            selectors = [
                "//a[contains(@id, 'Derechos')]",
                "//button[contains(text(), 'Derechos')]",
                "//a[contains(text(), 'Derechos')]",
                "//span[contains(text(), 'Derechos')]",
                "//li[@role='tab']//a[contains(text(), 'Derechos')]",
            ]
            
            for selector in selectors:
                try:
                    element = self.wait.until(EC.element_to_be_clickable((By.XPATH, selector)))
                    element.click()
                    logger.info("Clicked on 'Derechos e impuestos'")
                    time.sleep(2)
                    return True
                except:
                    continue
            
            logger.warning("Could not find 'Derechos e impuestos' tab")
            return False
            
        except Exception as e:
            logger.error(f"Error clicking 'Derechos e impuestos': {e}")
            return False

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
            
            # Try to click Derechos e impuestos
            self.click_derechos_e_impuestos()
            
            # Extract data
            data = self.extract_tariff_data()
            data["HS_Code"] = hs_code
            data["Status"] = "Success"
            
            logger.info(f"Successfully scraped HS Code: {hs_code}")
            return data
            
        except Exception as e:
            logger.error(f"Error scraping HS Code {hs_code}: {e}")
            return {"HS_Code": hs_code, "Status": f"Error: {str(e)}"}

    def scrape_multiple(self, hs_codes: List[str]):
        """Scrape multiple HS Codes"""
        try:
            self.navigate_to_portal()
            
            for hs_code in hs_codes:
                data = self.scrape_hs_code(hs_code)
                self.results.append(data)
                time.sleep(2)  # Delay between requests
            
            logger.info(f"Completed scraping {len(hs_codes)} HS Codes")
            
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
