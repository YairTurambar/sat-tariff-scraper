"""Export helpers for SAT tariff workbooks."""

__all__ = ["export_workbook"]


def __getattr__(name):
    if name == "export_workbook":
        from .excel import export_workbook

        return export_workbook
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
