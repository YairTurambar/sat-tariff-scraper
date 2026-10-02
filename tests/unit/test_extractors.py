from pathlib import Path

from sat_tariff.extractors.nomenclature import parse_nomenclature
from sat_tariff.extractors.quotas import NO_QUOTA_MESSAGE, parse_quotas
from sat_tariff.extractors.restrictions import parse_restrictions
from sat_tariff.extractors.rights_taxes import parse_rights_taxes

FIXTURES = Path("tests/fixtures")


def read_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_rights_taxes_preserves_titles_and_order():
    html = (
        "<table><tr><th>Foo</th><th>Bar</th></tr><tr><td>a</td><td>b</td></tr></table>"
        + read_fixture("rights_taxes.html")
    )
    result = parse_rights_taxes(html)
    assert result.status == "ok"
    assert [row.agreement_name for row in result.rows] == [
        "TRATAMIENTO GENERAL",
        "TRATAMIENTO GENERAL",
        "Tratado de Libre Comercio - MX",
    ]
    assert result.rows[2].value == "0%"


def test_nomenclature_parses_fields_and_units():
    result = parse_nomenclature(read_fixture("nomenclature.html"))
    assert result.status == "ok"
    goods = next(row for row in result.rows if row.record_type == "goods")
    unit = next(row for row in result.rows if row.record_type == "unit")
    extra = next(row for row in result.rows if row.record_type == "Clasificadores estadísticos")
    assert goods.section == "Sección I"
    assert goods.effective_from_normalized == "2024-01-01"
    assert goods.additional_codes_text == "No se han encontrado códigos adicionales asociados al inciso consultado"
    assert unit.unit_code == "KGM"
    assert unit.unit_description == "Kilogramo"
    assert extra.content == "No aplica"


def test_restrictions_with_no_data_store_literal_message():
    result = parse_restrictions(read_fixture("restrictions_empty.html"))
    assert result.status == "sin_informacion"
    assert result.rows[0].description == "sin información"


def test_restrictions_with_data_parse_rows():
    html = (
        "<table><tr><th>Código</th><th>Descripción</th></tr><tr><td>x</td><td>ignored</td></tr></table>"
        + read_fixture("restrictions_with_data.html")
    )
    result = parse_restrictions(html)
    assert result.status == "ok"
    assert len(result.rows) == 1
    assert result.rows[0].quota_code == "CQR"


def test_quotas_exact_no_quota_message_and_data_case():
    empty = parse_quotas(read_fixture("quotas_none.html"))
    assert empty.status == "no_quotas"
    assert empty.rows[0].message == NO_QUOTA_MESSAGE

    data = parse_quotas(read_fixture("quotas_with_data.html"))
    assert data.status == "ok"
    assert "Cupo anual" in data.rows[0].message
