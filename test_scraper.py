"""Unit tests for SAT tariff scraper."""

import os
import tempfile
import unittest

from bs4 import BeautifulSoup
from openpyxl import load_workbook

from sat_scraper import SECTION_LABELS, SATTariffScraper


class TestSATTariffScraper(unittest.TestCase):
    def setUp(self):
        self.scraper = SATTariffScraper()

    def test_sections_are_processed_in_requested_order(self):
        self.assertEqual(
            SECTION_LABELS,
            ("Derechos e impuestos", "Nomenclatura", "Restricciones", "Cuotas"),
        )

    def test_parse_all_tables_preserves_duplicate_rows(self):
        soup = BeautifulSoup(
            "<table><tr><th>Campo</th><th>Valor</th></tr>"
            "<tr><td>A</td><td>1</td></tr><tr><td>A</td><td>2</td></tr></table>",
            "html.parser",
        )
        data = self.scraper._parse_all_tables(soup)
        self.assertEqual(data["table_1_row_2_col_2"], "1")
        self.assertEqual(data["table_1_row_3_col_2"], "2")
        self.assertIn("label_A", data)
        self.assertIn("label_A_2", data)

    def test_section_data_includes_every_table_cell(self):
        soup = BeautifulSoup(
            "<table><tr><td>Restricción</td><td>Licencia previa</td></tr></table>",
            "html.parser",
        )
        data = self.scraper.extract_section_data.__self__._parse_all_tables(soup)
        self.assertEqual(data["table_1_row_1_col_1"], "Restricción")
        self.assertEqual(data["table_1_row_1_col_2"], "Licencia previa")

    def test_scrape_hs_code_retains_sections_separately(self):
        expected_data = {
            "Derechos e impuestos": {"duty_rate": "5%"},
            "Nomenclatura": {"description": "Producto"},
            "Restricciones": {"restriction": "Licencia previa"},
        }

        self.scraper.check_for_captcha = lambda: False
        self.scraper.enter_hs_code = lambda hs_code: True
        self.scraper.click_search_button = lambda: True
        self.scraper.extract_section_in_new_tab = lambda section_label: expected_data.get(section_label)

        result = self.scraper.scrape_hs_code("0101210000")

        self.assertEqual(result["Sections"]["Derechos e impuestos"]["duty_rate"], "5%")
        self.assertEqual(result["Sections"]["Nomenclatura"]["description"], "Producto")
        self.assertEqual(
            result["Sections"]["Restricciones"]["restriction"],
            "Licencia previa",
        )
        self.assertEqual(result["Sections"]["Cuotas"], {})
        self.assertEqual(result["Section_Statuses"]["Cuotas"], "Section extraction failed")
        self.assertEqual(result["Status"], "Missing sections: Cuotas")

    def test_scrape_hs_code_reflects_non_success_section_status(self):
        expected_data = {
            "Derechos e impuestos": {"duty_rate": "5%"},
            "Nomenclatura": {"status": "No data found"},
            "Restricciones": {"restriction": "Licencia previa"},
            "Cuotas": {"quota": "Sin cuota"},
        }

        self.scraper.check_for_captcha = lambda: False
        self.scraper.enter_hs_code = lambda hs_code: True
        self.scraper.click_search_button = lambda: True
        self.scraper.extract_section_in_new_tab = lambda section_label: expected_data[section_label]

        result = self.scraper.scrape_hs_code("0101210000")

        self.assertEqual(result["Section_Statuses"]["Nomenclatura"], "No data found")
        self.assertEqual(result["Status"], "Section issues: Nomenclatura: No data found")

    def test_export_to_excel_creates_section_worksheets(self):
        self.scraper.results = [
            {
                "HS_Code": "0101210000",
                "Status": "Success",
                "Sections": {
                    "Derechos e impuestos": {"duty_rate": "5%"},
                    "Nomenclatura": {"description": "Producto"},
                    "Restricciones": {"restriction": "Licencia previa"},
                    "Cuotas": {"quota": "Sin cuota"},
                },
                "Section_Statuses": {
                    section_label: "Success" for section_label in SECTION_LABELS
                },
            },
            {
                "HS_Code": "0102210000",
                "Status": "Missing sections: Cuotas",
                "Sections": {
                    "Derechos e impuestos": {"duty_rate": "10%"},
                    "Nomenclatura": {},
                    "Restricciones": {"restriction": "Ninguna"},
                    "Cuotas": {},
                },
                "Section_Statuses": {
                    "Derechos e impuestos": "Success",
                    "Nomenclatura": "No data found",
                    "Restricciones": "Success",
                    "Cuotas": "Section extraction failed",
                },
            },
        ]

        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as temp_file:
            output_file = temp_file.name

        try:
            self.scraper.export_to_excel(output_file)
            workbook = load_workbook(output_file)

            self.assertEqual(workbook.sheetnames, list(SECTION_LABELS))

            duties_sheet = workbook["Derechos e impuestos"]
            self.assertEqual(duties_sheet["A2"].value, "0101210000")
            self.assertEqual(duties_sheet["B2"].value, "Success")
            self.assertIn("duty_rate", [cell.value for cell in duties_sheet[1]])

            nomenclature_sheet = workbook["Nomenclatura"]
            self.assertEqual(nomenclature_sheet["A2"].value, "0101210000")
            self.assertEqual(nomenclature_sheet["A3"].value, "0102210000")
            self.assertEqual(nomenclature_sheet["B3"].value, "No data found")
            self.assertIn("description", [cell.value for cell in nomenclature_sheet[1]])

            restrictions_sheet = workbook["Restricciones"]
            self.assertEqual(restrictions_sheet["A3"].value, "0102210000")
            self.assertIn("restriction", [cell.value for cell in restrictions_sheet[1]])

            quotas_sheet = workbook["Cuotas"]
            self.assertEqual(quotas_sheet["A3"].value, "0102210000")
            self.assertEqual(quotas_sheet["B3"].value, "Section extraction failed")
            self.assertIn("quota", [cell.value for cell in quotas_sheet[1]])
        finally:
            if os.path.exists(output_file):
                os.remove(output_file)

    def test_empty_table_parse_returns_dict(self):
        self.assertIsInstance(self.scraper._parse_all_tables(BeautifulSoup("<html/>", "html.parser")), dict)


if __name__ == "__main__":
    unittest.main()
