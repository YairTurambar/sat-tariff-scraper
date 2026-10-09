"""Worksheet layout constants."""

SECTION_LABELS = ("Derechos e impuestos", "Nomenclatura", "Restricciones", "Cuotas")
STANDARD_SECTION_COLUMNS = ("Código", "Descripción", "Código adicional", "Valor", "Código de cuota")
QUOTA_EMPTY_MESSAGE = "No se han encontrado cuotas/contingentes para el inciso consultado"
DUTY_GROUP_ORDER_HINT = (
    "GENERAL",
    "MX",
    "CL",
    "AE",
    "CO",
    "UK",
    "US",
    "TW",
    "DO",
    "CU",
    "BZ",
    "EC",
    "PA",
    "IL",
)
FORBIDDEN_EXPORT_COLUMNS = {"Table_Name", "Record_Type", "Message", "Resultado", "Content", "Input_Index"}

SHEET_ORDER = list(SECTION_LABELS)
RIGHTS_BASE_HEADERS = ["HS_Code", "Status", "Overall_Status", "Código"]
RIGHTS_TRAILING_HEADERS = ["Código adicional", "Código de cuota"]
NOMENCLATURE_HEADERS = [
    "HS_Code",
    "Status",
    "Overall_Status",
    "Sección",
    "Capítulo:",
    "Fecha inicio de vigencia:",
    "Fecha fin de vigencia:",
    "Códigos adicionales",
    "Código",
    "Descripción",
]
RESTRICTIONS_HEADERS = [
    "HS_Code",
    "Status",
    "Overall_Status",
    "Código",
    "Descripción",
    "Código adicional",
    "Valor",
    "Código de cuota",
]
QUOTAS_HEADERS = ["HS_Code", "Status", "Overall_Status", "TRATAMIENTO GENERAL"]
TEXT_COLUMNS = {"HS_Code", "Código", "Código adicional", "Código de cuota"}
