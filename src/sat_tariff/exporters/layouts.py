"""Worksheet layout constants."""

SHEET_ORDER = ["Derechos e impuestos", "Nomenclatura", "Restricciones", "Cuotas"]
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
