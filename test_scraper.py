"""Unit tests for SAT tariff scraper."""

import unittest
from bs4 import BeautifulSoup
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

    def test_prefix_section_data(self):
        prefixed = self.scraper._prefix_section_data("Nomenclatura", {"field": "value"})
        self.assertEqual(prefixed, {"Nomenclatura__field": "value"})

    def test_empty_table_parse_returns_dict(self):
        self.assertIsInstance(self.scraper._parse_all_tables(BeautifulSoup("<html/>", "html.parser")), dict)


if __name__ == "__main__":
    unittest.main()
