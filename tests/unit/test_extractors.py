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


def test_restrictions_explicit_no_permits_is_success():
    from sat_tariff.extractors.restrictions import NO_RESTRICTIONS_MESSAGE

    result = parse_restrictions(read_fixture("restrictions_no_permits.html"))
    assert result.status == "ok"
    assert [row.to_dict() for row in result.rows] == [{
        "code": "", "description": NO_RESTRICTIONS_MESSAGE,
        "additional_code": "", "value": "", "quota_code": "", "source_status": "ok",
    }]
    assert parse_restrictions("<div>Unknown response</div>").status == "sin_informacion"


def test_structured_quotas_preserve_header_mapping_and_empty_cells():
    result = parse_quotas(read_fixture("quotas_structured.html"))
    assert result.status == "ok"
    assert len(result.rows) == 2
    first, second = result.rows
    assert first.general_treatment == "0210.11.0000 | - - Jamones, paletas y sus trozos, sin deshuesar"
    assert (first.quota, first.country, first.effective_from, first.effective_to,
            first.initial_quantity, first.exhaustion_date, first.variation) == (
        "Cuota 1", "Guatemala", "01/01/2024", "31/12/2024", "100", "30/11/2024", "5%",
    )
    assert second.general_treatment == first.general_treatment
    assert first.extensions == second.extensions == ""
    assert (second.quota, second.country, second.effective_from, second.effective_to,
            second.initial_quantity, second.exhaustion_date, second.variation) == (
        "Cuota 2", "", "01/01/2025", "", "200", "", "0%",
    )


def test_sat_ca108_all_ten_vigencies_remain_in_source_order():
    result = parse_quotas(read_fixture("quotas_sat_ca108.html"))
    assert result.status == "ok"
    assert len(result.rows) == 10
    assert [row.effective_from for row in result.rows] == [
        "1/1/2023", "1/12/2013", "1/1/2018", "1/1/2016", "1/1/2026",
        "1/1/2019", "1/1/2014", "1/1/2022", "1/1/2017", "1/1/2024",
    ]
    assert [row.initial_quantity for row in result.rows] == [
        "1350000 KGS", "900000 KGS", "1125000 KGS", "1035000 KGS", "1485000 KGS",
        "1125000 KGS", "945000 KGS", "1305000 KGS", "1080000 KGS", "1395000 KGS",
    ]
    assert all(row.quota == "CA108" for row in result.rows)
    assert all(row.country == row.exhaustion_date == row.variation == row.extensions == "" for row in result.rows)


def test_sat_headerless_inciso_populates_general_treatment():
    html = read_fixture("quota_goods_sat.html") + read_fixture("quotas_sat_ca108.html")
    result = parse_quotas(html)
    assert result.status == "ok"
    assert len(result.rows) == 10
    expected = "0210.11.0000 | - - Jamones, paletas y sus trozos, sin deshuesar"
    assert all(row.general_treatment == expected for row in result.rows)


def test_sat_subpartidas_are_not_exported_as_the_queried_inciso():
    from sat_tariff.extractors.common import parse_html

    goods = parse_html(read_fixture("quota_goods_sat.html"))
    goods.select_one('table[id$=":incisosTable"]').decompose()
    result = parse_quotas(str(goods) + read_fixture("quotas_sat_ca108.html"))
    assert result.status == "ok"
    assert len(result.rows) == 10
    assert all(row.general_treatment == "" for row in result.rows)


def test_sat_headerless_fallback_does_not_replace_valid_labeled_goods():
    html = read_fixture("quotas_structured.html") + read_fixture("quota_goods_sat.html").replace(
        "0210.11.0000", "0210.12.0000",
    )
    result = parse_quotas(html)
    assert result.status == "ok"
    assert all(row.general_treatment.startswith("0210.11.0000 | ") for row in result.rows)


@pytest.mark.parametrize("row_index", [0, 5, 9])
def test_quota_popup_is_extracted_only_from_its_own_row(row_index):
    from sat_tariff.extractors.common import parse_html

    soup = parse_html(read_fixture("quotas_sat_ca108.html"))
    cell = soup.select("tbody > tr")[row_index].find_all("td", recursive=False)[-1]
    cell.append(parse_html(read_fixture("quota_extensions_popup.html")))
    result = parse_quotas(str(soup))
    assert result.status == "ok"
    assert len(result.rows) == 10
    expected = "Ampliaciones de la cuota en la vigencia definida\nNo tiene ampliaciones definidas"
    assert [row.extensions for row in result.rows] == [
        expected if index == row_index else "" for index in range(10)
    ]
    assert all(row.quota == "CA108" for row in result.rows)
    assert all("Ver ampliaciones" not in row.extensions for row in result.rows)


def test_unrecognized_nested_quota_table_does_not_drop_the_parent_row():
    html = read_fixture("quotas_sat_ca108.html").replace(
        "<td></td></tr>", "<td><table><tr><td>Unknown popup</td></tr></table></td></tr>", 1,
    )
    result = parse_quotas(html)
    assert result.status == "extraction_error"
    assert result.rows == []
    assert result.message == "Unrecognized nested quota table"


def test_quotas_match_reordered_headers_and_ignore_layout_tables():
    html = read_fixture("quotas_structured.html")
    html = html.replace("<th>Cuota</th><th>País</th>", "<th>PAIS</th><th>CUOTA</th>")
    html = html.replace("<td>Cuota 1</td><td>Guatemala</td>", "<td>Guatemala</td><td>Cuota 1</td>")
    html = html.replace("<td>Cuota 2</td><td></td>", "<td></td><td>Cuota 2</td>")
    result = parse_quotas(f"<table><tr><td>{html}</td></tr></table>")
    assert len(result.rows) == 2
    assert result.rows[0].quota == "Cuota 1"
    assert result.rows[0].country == "Guatemala"
    single = parse_quotas(html.replace(
        '<tr><td></td><td>Cuota 2</td><td>01/01/2025</td><td></td><td>200</td><td></td><td>0%</td></tr>', ""
    ))
    assert len(single.rows) == 1


@pytest.mark.parametrize("old,new", [
    ("<th>Inicio vigencia</th>", "<th>Inicio desconocido</th>"),
    ("<td>Guatemala</td>", ""),
    ("<td>Guatemala</td>", '<td colspan="2">Guatemala</td>'),
])
def test_malformed_quota_tables_are_recoverable_errors(old, new):
    html = read_fixture("quotas_structured.html").replace(old, new)
    result = parse_quotas(html)
    assert result.status == "extraction_error"
    assert result.rows == []
    assert result.message


@pytest.mark.parametrize("old,new", [
    ("<th>País</th>", "<th>Origen desconocido</th>"),
    ("<th>Cuota</th>", "<th>Identificador desconocido</th>"),
])
def test_mixed_valid_and_invalid_quota_tables_cannot_checkpoint_partial_results(old, new):
    html = read_fixture("quotas_structured.html")
    result = parse_quotas(html + html.replace(old, new))
    assert result.status == "extraction_error"
    assert result.rows == []
    assert result.message == "Quota headers not recognized"


def test_empty_captioned_goods_table_does_not_borrow_unit_rows():
    html = (
        "<table><caption>Código de Mercancías</caption>"
        "<tr><th>Código</th><th>Descripción</th></tr></table>"
        "<table><caption>Unidades de medida</caption>"
        "<tr><th>Código</th><th>Descripción</th></tr>"
        "<tr><td>KGM</td><td>Kilogramo</td></tr></table>"
    )
    result = parse_nomenclature(html)
    assert result.status == "ok"
    assert [row.record_type for row in result.rows] == ["unit"]


def test_nomenclature_caption_headers_and_partial_scalars():
    result = parse_nomenclature(read_fixture("nomenclature_caption.html"))
    assert result.status == "ok"
    assert [row.record_type for row in result.rows] == ["goods", "unit"]
    assert result.rows[0].code == "0210.11.0000"
    assert result.rows[1].unit_code == "KGM"
    assert all(row.section == "Sección I" for row in result.rows)
    assert all(
        row.additional_codes_text == "No se han encontrado códigos adicionales asociados al inciso consultado"
        for row in result.rows
    )
    partial = parse_nomenclature(read_fixture("nomenclature_partial.html"))
    assert partial.status == "ok"
    assert partial.rows[0].record_type == "summary"
    assert partial.rows[0].source_status == "ok"
    assert partial.rows[0].chapter == "Capítulo 02"


@pytest.mark.parametrize("html", [
    read_fixture("session_expired.html"),
    "<h1>Error del servidor</h1>",
    "<div>CAPTCHA requerido</div>",
    "<html><table><tr><td>Unrecognized</td></tr></table></html>",
    "",
])
def test_nomenclature_and_quotas_do_not_accept_invalid_responses(html):
    assert parse_nomenclature(html).status not in {"ok", "empty"}
    assert parse_quotas(html).status not in {"ok", "no_quotas"}


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
