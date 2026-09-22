"""Unit tests for SAT tariff scraper."""

import os
import tempfile
import unittest

from bs4 import BeautifulSoup
from openpyxl import load_workbook

from sat_scraper import (
    SECTION_LABELS,
    SECTION_ROWS_KEY,
    SECTION_STATUS_KEY,
    SATTariffScraper,
)


class TestSATTariffScraper(unittest.TestCase):
    def setUp(self):
        self.scraper = SATTariffScraper()

    def test_sections_are_processed_in_requested_order(self):
        self.assertEqual(
            SECTION_LABELS,
            ("Derechos e impuestos", "Nomenclatura", "Restricciones", "Cuotas"),
        )

    def test_parse_nomenclature_extracts_named_fields_and_messages(self):
        soup = BeautifulSoup(
            """
            <table>
              <tr><td>Sección</td><td>Sección I</td></tr>
              <tr><td>Capítulo:</td><td>Capítulo 01</td></tr>
              <tr><td>Fecha inicio de vigencia:</td><td>2024-01-01</td></tr>
              <tr><td>Fecha fin de vigencia:</td><td>2024-12-31</td></tr>
            </table>
            <h3>Código de Mercancías</h3>
            <table>
              <tr><th>Código</th><th>Descripción</th><th>Notas</th></tr>
              <tr><td>0101</td><td>Caballos</td><td>Vivo</td></tr>
            </table>
            <h3>Códigos adicionales</h3>
            <p>No se han encontrado códigos adicionales asociados al inciso consultado</p>
            <h3>Unidades de medida</h3>
            <table>
              <tr><th>Código</th><th>Descripción</th><th>Extra</th></tr>
              <tr><td>KGM</td><td>Kilogramo</td><td>Ignorar</td></tr>
            </table>
            <h3>Clasificadores estadísticos</h3>
            <p>No aplica</p>
            <h3>Descripciones mínimas</h3>
            <p>Sin descripción mínima</p>
            <h3>Criterios de Clasificación</h3>
            <p>Según nota legal</p>
            """,
            "html.parser",
        )

        data = self.scraper._parse_nomenclature(soup)
        rows = data[SECTION_ROWS_KEY]

        mercancías_row = next(row for row in rows if row["Table_Name"] == "Código de Mercancías")
        self.assertEqual(mercancías_row["Sección"], "Sección I")
        self.assertEqual(mercancías_row["Capítulo:"], "Capítulo 01")
        self.assertEqual(mercancías_row["Fecha inicio de vigencia:"], "2024-01-01")
        self.assertEqual(mercancías_row["Fecha fin de vigencia:"], "2024-12-31")
        self.assertEqual(mercancías_row["Código"], "0101")
        self.assertEqual(mercancías_row["Descripción"], "Caballos")
        self.assertEqual(mercancías_row["Notas"], "Vivo")

        additional_codes_row = next(row for row in rows if row["Table_Name"] == "Códigos adicionales")
        self.assertEqual(
            additional_codes_row["Message"],
            "No se han encontrado códigos adicionales asociados al inciso consultado",
        )

        units_row = next(row for row in rows if row["Table_Name"] == "Unidades de medida")
        self.assertEqual(units_row["Código"], "KGM")
        self.assertEqual(units_row["Descripción"], "Kilogramo")
        self.assertNotIn("Extra", units_row)

        self.assertIn(
            {
                "Sección": "Sección I",
                "Capítulo:": "Capítulo 01",
                "Fecha inicio de vigencia:": "2024-01-01",
                "Fecha fin de vigencia:": "2024-12-31",
                "Record_Type": "Clasificadores estadísticos",
                "Table_Name": "Clasificadores estadísticos",
                "Content": "No aplica",
            },
            rows,
        )
        self.assertIsNone(data[SECTION_STATUS_KEY])

    def test_parse_duties_preserves_duplicate_and_agreement_rows(self):
        soup = BeautifulSoup(
            """
            <h3>TRATAMIENTO GENERAL</h3>
            <table>
              <tr>
                <th>Código</th><th>Descripción</th><th>Código adicional</th>
                <th>Valor</th><th>Código de cuota</th>
              </tr>
              <tr><td>A1</td><td>IVA</td><td>AD1</td><td>12%</td><td>CQ1</td></tr>
              <tr><td>A1</td><td>IVA</td><td>AD1</td><td>12%</td><td>CQ1</td></tr>
            </table>
            <h3>TLC Guatemala</h3>
            <table>
              <tr>
                <th>Código</th><th>Descripción</th><th>Código adicional</th>
                <th>Valor</th><th>Código de cuota</th>
              </tr>
              <tr><td>B2</td><td>Preferencial</td><td>AD2</td><td>0%</td><td>CQ2</td></tr>
            </table>
            """,
            "html.parser",
        )

        data = self.scraper._parse_standard_section(soup)
        rows = data[SECTION_ROWS_KEY]

        self.assertEqual(len(rows), 3)
        self.assertEqual(sum(1 for row in rows if row["Código"] == "A1"), 2)
        self.assertEqual(rows[0]["Table_Name"], "TRATAMIENTO GENERAL")
        self.assertEqual(rows[0]["Código de cuota"], "CQ1")
        self.assertEqual(rows[2]["Table_Name"], "TLC Guatemala")
        self.assertEqual(rows[2]["Valor"], "0%")

    def test_parse_restrictions_general_rows_include_quota_code(self):
        soup = BeautifulSoup(
            """
            <h3>TRATAMIENTO GENERAL</h3>
            <table>
              <tr>
                <th>Código</th><th>Descripción</th><th>Código adicional</th>
                <th>Valor</th><th>Código de cuota</th>
              </tr>
              <tr><td>R1</td><td>Licencia previa</td><td>AD3</td><td>Obligatoria</td><td>CQR</td></tr>
            </table>
            """,
            "html.parser",
        )

        data = self.scraper._parse_standard_section(soup)
        self.assertEqual(
            data[SECTION_ROWS_KEY],
            [
                {
                    "Table_Name": "TRATAMIENTO GENERAL",
                    "Código": "R1",
                    "Descripción": "Licencia previa",
                    "Código adicional": "AD3",
                    "Valor": "Obligatoria",
                    "Código de cuota": "CQR",
                }
            ],
        )

    def test_parse_quotas_empty_message_when_no_rows_exist(self):
        soup = BeautifulSoup(
            """
            <div>No se han encontrado cuotas/contingentes para el inciso consultado</div>
            """,
            "html.parser",
        )

        data = self.scraper._parse_standard_section(
            soup,
            empty_message="No se han encontrado cuotas/contingentes para el inciso consultado",
        )

        self.assertEqual(
            data[SECTION_ROWS_KEY],
            [
                {
                    "Table_Name": "TRATAMIENTO GENERAL",
                    "Message": "No se han encontrado cuotas/contingentes para el inciso consultado",
                }
            ],
        )
        self.assertIsNone(data[SECTION_STATUS_KEY])

    def test_scrape_hs_code_reflects_non_success_section_status(self):
        expected_data = {
            "Derechos e impuestos": {SECTION_ROWS_KEY: [{"Table_Name": "TRATAMIENTO GENERAL"}]},
            "Nomenclatura": {SECTION_ROWS_KEY: [], SECTION_STATUS_KEY: "No data found"},
            "Restricciones": {SECTION_ROWS_KEY: [{"Table_Name": "TRATAMIENTO GENERAL"}]},
            "Cuotas": {SECTION_ROWS_KEY: [{"Table_Name": "TRATAMIENTO GENERAL", "Message": "Sin cuota"}]},
        }

        self.scraper.check_for_captcha = lambda: False
        self.scraper.enter_hs_code = lambda hs_code: True
        self.scraper.click_search_button = lambda: True
        self.scraper.extract_section_in_new_tab = lambda section_label: expected_data[section_label]

        result = self.scraper.scrape_hs_code("0101210000")

        self.assertEqual(result["Section_Statuses"]["Nomenclatura"], "No data found")
        self.assertEqual(result["Status"], "Section issues: Nomenclatura: No data found")

    def test_export_to_excel_creates_section_worksheets_with_status_columns(self):
        self.scraper.results = [
            {
                "HS_Code": "0101210000",
                "Status": "Success",
                "Sections": {
                    "Derechos e impuestos": {
                        SECTION_ROWS_KEY: [
                            {
                                "Table_Name": "TRATAMIENTO GENERAL",
                                "Código": "A1",
                                "Descripción": "IVA",
                                "Código adicional": "AD1",
                                "Valor": "12%",
                                "Código de cuota": "CQ1",
                            },
                            {
                                "Table_Name": "TLC Guatemala",
                                "Código": "B2",
                                "Descripción": "Preferencial",
                                "Código adicional": "AD2",
                                "Valor": "0%",
                                "Código de cuota": "CQ2",
                            },
                        ]
                    },
                    "Nomenclatura": {
                        SECTION_ROWS_KEY: [
                            {
                                "Table_Name": "Código de Mercancías",
                                "Record_Type": "Código de Mercancías",
                                "Sección": "Sección I",
                                "Capítulo:": "Capítulo 01",
                                "Fecha inicio de vigencia:": "2024-01-01",
                                "Fecha fin de vigencia:": "2024-12-31",
                                "Código": "0101",
                                "Descripción": "Caballos",
                            }
                        ]
                    },
                    "Restricciones": {
                        SECTION_ROWS_KEY: [
                            {
                                "Table_Name": "TRATAMIENTO GENERAL",
                                "Código": "R1",
                                "Descripción": "Licencia previa",
                                "Código adicional": "AD3",
                                "Valor": "Obligatoria",
                                "Código de cuota": "CQR",
                            }
                        ]
                    },
                    "Cuotas": {
                        SECTION_ROWS_KEY: [
                            {
                                "Table_Name": "TRATAMIENTO GENERAL",
                                "Message": "No se han encontrado cuotas/contingentes para el inciso consultado",
                            }
                        ]
                    },
                },
                "Section_Statuses": {section_label: "Success" for section_label in SECTION_LABELS},
            }
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
            self.assertEqual(duties_sheet["A3"].value, "0101210000")
            self.assertIn("Código de cuota", [cell.value for cell in duties_sheet[1]])

            nomenclature_sheet = workbook["Nomenclatura"]
            self.assertEqual(nomenclature_sheet["A2"].value, "0101210000")
            self.assertIn("Sección", [cell.value for cell in nomenclature_sheet[1]])

            restrictions_sheet = workbook["Restricciones"]
            self.assertEqual(restrictions_sheet["A2"].value, "0101210000")
            self.assertIn("Código de cuota", [cell.value for cell in restrictions_sheet[1]])

            quotas_sheet = workbook["Cuotas"]
            self.assertEqual(quotas_sheet["A2"].value, "0101210000")
            self.assertEqual(quotas_sheet["B2"].value, "Success")
            self.assertIn("Message", [cell.value for cell in quotas_sheet[1]])
        finally:
            if os.path.exists(output_file):
                os.remove(output_file)

    def test_export_to_excel_uses_overall_status_for_unattempted_sections(self):
        self.scraper.results = [
            {
                "HS_Code": "0101210000",
                "Status": "Failed to submit HS code",
                "Sections": {section_label: {} for section_label in SECTION_LABELS},
                "Section_Statuses": {},
            }
        ]

        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as temp_file:
            output_file = temp_file.name

        try:
            self.scraper.export_to_excel(output_file)
            workbook = load_workbook(output_file)

            for section_label in SECTION_LABELS:
                sheet = workbook[section_label]
                self.assertEqual(sheet["A2"].value, "0101210000")
                self.assertEqual(sheet["B2"].value, "Failed to submit HS code")
                self.assertEqual(sheet["C2"].value, "Failed to submit HS code")
        finally:
            if os.path.exists(output_file):
                os.remove(output_file)


if __name__ == "__main__":
    unittest.main()
