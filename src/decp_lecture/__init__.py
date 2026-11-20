"""Lire les DECP consolidées sans se tromper : les règles de lecture, en DuckDB."""

from .lecture import (
    JEU_DECP,
    REGLES,
    adresse_parquet,
    charger_sirene,
    choisir_ressource,
    journal,
    ouvrir,
    telecharger,
)

__all__ = [
    "JEU_DECP",
    "REGLES",
    "adresse_parquet",
    "charger_sirene",
    "choisir_ressource",
    "journal",
    "ouvrir",
    "telecharger",
]
__version__ = "0.1.0"
