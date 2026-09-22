"""Unit tests for SAT tariff scraper."""

import os
import tempfile
import unittest
from unittest import mock

from bs4 import BeautifulSoup
from openpyxl import load_workbook

from main import build_argument_parser, load_hs_codes_from_file
from sat_scraper import (
    SECTION_LABELS,
    SECTION_ROWS_KEY,
    SECTION_STATUS_KEY,
    SATTariffScraper,
)


class TestSATTariffScraper(unittest.TestCase):
    def setUp(self):
        self.scraper = SATTariffScraper()

    @staticmethod
    def _result_for(hs_code, status):
        return {
            "HS_Code": hs_code,
            "Status": status,
            "Sections": {section_label: {} for section_label in SECTION_LABELS},
            "Section_Statuses": (
                {section_label: "Success" for section_label in SECTION_LABELS}
                if status == "Success"
                else {}
            ),
        }

    def test_load_hs_codes_from_file_supports_arbitrary_counts_without_cap(self):
        for count in (0, 1, 19, 20, 25):
            with self.subTest(count=count):
                codes = [f"{1000000000 + index:010d}" for index in range(count)]
                with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as temp_file:
                    temp_file.write("number\n")
                    temp_file.write("\n".join(codes))
                    input_path = temp_file.name

                try:
                    self.assertEqual(load_hs_codes_from_file(input_path), codes)
                finally:
                    os.remove(input_path)

    def test_argument_parser_accepts_resume_delay_and_retry_options(self):
        args = build_argument_parser().parse_args(
            [
                "hs_codes.txt",
                "output.xlsx",
                "--resume",
                "--state-file",
                "state.json",
                "--delay-between-codes",
                "1.5",
                "--max-retries",
                "3",
                "--retry-backoff",
                "4",
            ]
        )

        self.assertEqual(args.hs_codes_file, "hs_codes.txt")
        self.assertEqual(args.output_file, "output.xlsx")
        self.assertTrue(args.resume)
        self.assertEqual(args.state_file, "state.json")
        self.assertEqual(args.delay_between_codes, 1.5)
        self.assertEqual(args.max_retries, 3)
        self.assertEqual(args.retry_backoff, 4)

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

    def test_scrape_multiple_continues_after_failed_code_with_bounded_retries(self):
        scraper = SATTariffScraper(delay_between_codes=0, max_retries=2, retry_backoff=0)
        scraper.navigate_to_portal = lambda: None
        scraper.export_to_excel = lambda output_file: None
        attempts = []
        outcomes = {
            "0101210000": [
                self._result_for("0101210000", "Failed to submit HS code"),
                self._result_for("0101210000", "Failed to submit HS code"),
                self._result_for("0101210000", "Failed to submit HS code"),
            ],
            "0102210000": [self._result_for("0102210000", "Success")],
        }

        def fake_scrape_hs_code(hs_code):
            attempts.append(hs_code)
            return outcomes[hs_code].pop(0)

        scraper.scrape_hs_code = fake_scrape_hs_code

        scraper.scrape_multiple(
            ["0101210000", "0102210000"],
            output_file="/tmp/test-output.xlsx",
        )

        self.assertEqual(
            attempts,
            ["0101210000", "0101210000", "0101210000", "0102210000"],
        )
        self.assertEqual([result["HS_Code"] for result in scraper.results], ["0101210000", "0102210000"])
        self.assertEqual(scraper.results[0]["Status"], "Failed to submit HS code")
        self.assertEqual(scraper.results[1]["Status"], "Success")

    def test_scrape_multiple_does_not_retry_captcha_failures(self):
        scraper = SATTariffScraper(delay_between_codes=0, max_retries=3, retry_backoff=0)
        scraper.navigate_to_portal = lambda: None
        scraper.export_to_excel = lambda output_file: None
        attempts = []

        def fake_scrape_hs_code(hs_code):
            attempts.append(hs_code)
            return self._result_for(hs_code, "CAPTCHA solving failed")

        scraper.scrape_hs_code = fake_scrape_hs_code

        scraper.scrape_multiple(
            ["0101210000", "0102210000"],
            output_file="/tmp/test-output.xlsx",
        )

        self.assertEqual(attempts, ["0101210000"])
        self.assertEqual(len(scraper.results), 1)
        self.assertEqual(scraper.results[0]["Status"], "CAPTCHA solving failed")

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

    def test_run_resume_skips_successful_codes_retries_failed_codes_and_preserves_order(self):
        successful = self._result_for("0101210000", "Success")
        failed = self._result_for("0102210000", "Failed to submit HS code")

        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as output_handle:
            output_file = output_handle.name
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as state_handle:
            state_file = state_handle.name

        try:
            seed_scraper = SATTariffScraper()
            seed_scraper.input_order = ["0101210000", "0102210000", "0103210000"]
            seed_scraper.results = [successful, failed]
            seed_scraper.save_state(state_file, output_file)

            scraper = SATTariffScraper(delay_between_codes=0, max_retries=0, retry_backoff=0)
            scraper.start_browser = lambda: None
            scraper.close_browser = lambda: None
            scraper.navigate_to_portal = lambda: None
            attempted_codes = []

            def fake_scrape_hs_code(hs_code):
                attempted_codes.append(hs_code)
                return self._result_for(hs_code, "Success")

            scraper.scrape_hs_code = fake_scrape_hs_code

            scraper.run(
                ["0101210000", "0102210000", "0103210000"],
                output_file=output_file,
                resume=True,
                state_file=state_file,
            )

            self.assertEqual(attempted_codes, ["0102210000", "0103210000"])
            self.assertEqual(
                [result["HS_Code"] for result in scraper.results],
                ["0101210000", "0102210000", "0103210000"],
            )
            self.assertEqual(
                [result["Status"] for result in scraper.results],
                ["Success", "Success", "Success"],
            )

            workbook = load_workbook(output_file)
            self.assertEqual(workbook.sheetnames, list(SECTION_LABELS))
            for section_label in SECTION_LABELS:
                sheet = workbook[section_label]
                self.assertEqual(
                    [sheet[f"A{row}"].value for row in range(2, 5)],
                    ["0101210000", "0102210000", "0103210000"],
                )
        finally:
            if os.path.exists(output_file):
                os.remove(output_file)
            if os.path.exists(state_file):
                os.remove(state_file)

    def test_run_with_no_codes_creates_empty_four_sheet_workbook(self):
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as output_handle:
            output_file = output_handle.name
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as state_handle:
            state_file = state_handle.name

        try:
            scraper = SATTariffScraper()
            scraper.start_browser = mock.Mock()
            scraper.run([], output_file=output_file, state_file=state_file)

            scraper.start_browser.assert_not_called()
            workbook = load_workbook(output_file)
            self.assertEqual(workbook.sheetnames, list(SECTION_LABELS))
        finally:
            if os.path.exists(output_file):
                os.remove(output_file)
            if os.path.exists(state_file):
                os.remove(state_file)


if __name__ == "__main__":
    unittest.main()
