from pathlib import Path

import pytest

from sat_tariff.extractors.nomenclature import parse_nomenclature
from sat_tariff.extractors.quotas import NO_QUOTA_MESSAGE, parse_quotas
from sat_tariff.extractors.restrictions import parse_restrictions
from sat_tariff.extractors.rights_taxes import (
    SAT_AGREEMENT_COLUMN_MAP,
    agreement_column_name,
    is_positional_identity,
    is_valid_agreement_identity,
    parse_rights_taxes,
)

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


@pytest.mark.parametrize(
    ("agreement_name", "column_name"),
    [
        (
            "Acuerdo de Alcance Parcial entre el Gobierno de la República de Guatemala y el Gobierno de Belice - BZ",
            "DAI_BZ",
        ),
        ("Tratado de Libre Comercio Entre Centroamérica y Chile - CL", "DAI_CL"),
        (
            "Tratado de Libre Comercio entre la República de Colombia y las Repúblicas de El Salvador, Guatemala y Honduras - CO",
            "DAI_CO",
        ),
        (
            "Tratado de Libre Comercio - República Dominicana - Centroamérica - Estados Unidos de América - US",
            "DAI_US",
        ),
        (
            "Acuerdo de Alcance Parcial entre la República de Guatemala y la República de Cuba - CU",
            "DAI_CU",
        ),
        (
            "Tratado de Libre Comercio entre Centroamérica y República Dominicana - DO",
            "DAI_DO",
        ),
        (
            "Acuerdo de Alcance Parcial de Complementación entre el Gobierno de la República de Guatemala y el Gobierno de la República del Ecuador - EC",
            "DAI_EC",
        ),
        (
            "Acuerdo por el que se establece una Asociación entre la Unión Europea y sus Estados Miembros, por un lado, y Centroamérica, por otro (UE) - ADAE",
            "DAI_AE",
        ),
        (
            "Tratado de Libre Comercio Entre Los Estados Unidos Mexicanos y las Repúblicas de Costa Rica, El Salvador, Guatemala, Honduras y Nicaragua - MX",
            "DAI_MX",
        ),
        (
            "Tratado de Libre Comercio y de Intercambio Preferencial entre las Repúblicas de Panamá y Guatemala - PA",
            "DAI_PA",
        ),
        (
            "Tratado de Libre Comercio entre la República de Guatemala y la República de China (Taiwán) - TW",
            "DAI_TW",
        ),
        (
            "Acuerdo por el que se Establece una Asociación Entre Reino Unido de Gran Bretaña e Irlanda del Norte y Centroamérica - UK",
            "DAI_UK",
        ),
        (
            "Tratado de Libre Comercio entre el Gobierno de la República de Guatemala y el Gobierno del Estado de Israel - IL",
            "DAI_IL",
        ),
    ],
)
def test_agreement_names_use_required_columns(agreement_name, column_name):
    assert agreement_column_name(agreement_name) == column_name


def test_agreement_matching_normalizes_case_accents_spacing_and_hyphens():
    variant = (
        "  TRATADO  DE LIBRE COMERCIO ENTRE LOS ESTADOS UNIDOS MEXICANOS "
        "Y LAS REPUBLICAS DE COSTA RICA, EL SALVADOR, GUATEMALA, HONDURAS "
        "Y NICARAGUA — MX  "
    )

    assert agreement_column_name(variant) == "DAI_MX"
    assert agreement_column_name("TRATAMIENTO GENERAL", "IVA") == "IVA_GENERAL"


def test_mapped_agreement_keeps_distinct_duty_and_tax_codes():
    agreement_name = (
        "Acuerdo de Alcance Parcial entre el Gobierno de la República de Guatemala "
        "y el Gobierno de Belice - BZ"
    )

    assert agreement_column_name(agreement_name, "DAI") == "DAI_BZ"
    assert agreement_column_name(agreement_name, "IVA") == "IVA_BZ"


def test_unknown_agreement_uses_only_an_explicit_trailing_code():
    assert agreement_column_name("Nuevo Acuerdo Comercial – XY") == "DAI_XY"
    assert agreement_column_name("Acuerdo México sin código") is None


def test_rights_taxes_preserves_long_official_agreement_title():
    agreement_name = (
        "Acuerdo por el que se establece una Asociación entre la Unión Europea "
        "y sus Estados Miembros, por un lado, y Centroamérica, por otro (UE) - ADAE"
    )
    html = (
        f"<h3>{agreement_name}</h3><table>"
        "<tr><th>Código</th><th>Descripción</th><th>Valor</th></tr>"
        "<tr><td>DAI</td><td>Preferencial</td><td>0%</td></tr></table>"
    )

    result = parse_rights_taxes(html)

    assert result.rows[0].agreement_name == agreement_name
    assert agreement_column_name(result.rows[0].agreement_name) == "DAI_AE"


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


def test_rights_taxes_resolves_every_official_agreement_from_jsf_structure():
    result = parse_rights_taxes(read_fixture("rights_taxes_jsf.html"))

    assert result.status == "ok"
    columns = [agreement_column_name(row.agreement_name, row.code) for row in result.rows]
    assert columns[:2] == ["DAI_GENERAL", "IVA_GENERAL"]
    assert set(columns) == {"DAI_GENERAL", "IVA_GENERAL"} | set(SAT_AGREEMENT_COLUMN_MAP.values())
    assert None not in columns
    assert not any(is_positional_identity(row.agreement_name) for row in result.rows)
    general_rows = [row for row in result.rows if row.agreement_name == "TRATAMIENTO GENERAL"]
    assert {row.code: row.value for row in general_rows} == {"DAI": "10%", "IVA": "12%"}
    belize = next(row for row in result.rows if agreement_column_name(row.agreement_name) == "DAI_BZ")
    mexico = next(row for row in result.rows if agreement_column_name(row.agreement_name) == "DAI_MX")
    assert belize.value == "0%"
    assert mexico.value == "5%"


def test_rights_taxes_nested_table_does_not_borrow_another_agreement_title():
    result = parse_rights_taxes(read_fixture("rights_taxes_jsf.html"))

    names = [row.agreement_name for row in result.rows]
    # Each rates table keeps its own identity: the only repeated name is the
    # general treatment, which legitimately owns the DAI and IVA rows.
    assert len([name for name in names if name == "TRATAMIENTO GENERAL"]) == 2
    assert len(set(names)) == len(SAT_AGREEMENT_COLUMN_MAP) + 1


def test_rights_taxes_resolves_title_beyond_the_old_twenty_node_limit():
    agreement_name = (
        "Acuerdo por el que se establece una Asociación entre la Unión Europea "
        "y sus Estados Miembros, por un lado, y Centroamérica, por otro (UE) - ADAE"
    )
    filler = "".join(f"<div><span></span></div>" for _ in range(40))
    html = (
        f"<h3>{agreement_name}</h3>{filler}"
        "<table><tr><th>Código</th><th>Descripción</th><th>Valor</th></tr>"
        "<tr><td>DAI</td><td>Preferencial</td><td>0%</td></tr></table>"
    )

    result = parse_rights_taxes(html)

    assert result.rows[0].agreement_name == agreement_name


def test_rights_taxes_reports_unresolvable_tables_instead_of_positional_identities():
    result = parse_rights_taxes(read_fixture("rights_taxes_unresolvable.html"))

    assert result.status == "incomplete"
    assert result.rows == []
    assert "reextraer" in (result.message or "")
    assert "DAI" in (result.message or "")


def test_positional_labels_are_never_valid_agreement_identities():
    for label in ("Tabla 14", "tabla  17", "TABLA17", "Table 3"):
        assert is_positional_identity(label) is True
        assert is_valid_agreement_identity(label) is False
    assert is_positional_identity("TRATAMIENTO GENERAL") is False
    assert is_valid_agreement_identity("TRATAMIENTO GENERAL") is True
    assert is_valid_agreement_identity("Código") is False
    assert is_valid_agreement_identity("") is False
