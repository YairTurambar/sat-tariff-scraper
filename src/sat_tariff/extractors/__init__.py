"""Pure HTML extractors for SAT sections."""

from .nomenclature import parse_nomenclature
from .quotas import parse_quotas
from .restrictions import parse_restrictions
from .rights_taxes import parse_rights_taxes

__all__ = [
    "parse_rights_taxes",
    "parse_nomenclature",
    "parse_restrictions",
    "parse_quotas",
]
