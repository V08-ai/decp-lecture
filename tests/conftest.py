"""Un petit decp.parquet fabriqué à la main, avec les colonnes du vrai fichier."""

from datetime import date

import duckdb
import pytest

COLONNES = {
    "uid": "VARCHAR",
    "donneesActuelles": "BOOLEAN",
    "dateNotification": "DATE",
    "acheteur_id": "VARCHAR",
    "acheteur_nom": "VARCHAR",
    "acheteur_departement_code": "VARCHAR",
    "titulaire_id": "VARCHAR",
    "titulaire_typeIdentifiant": "VARCHAR",
    "titulaire_nom": "VARCHAR",
    "titulaire_categorie": "VARCHAR",
    "titulaire_departement_code": "VARCHAR",
    "objet": "VARCHAR",
    "codeCPV": "VARCHAR",
    "nature": "VARCHAR",
    "procedure": "VARCHAR",
    "formePrix": "VARCHAR",
    "ccag": "VARCHAR",
    "typeGroupementOperateurs": "VARCHAR",
    "considerationsSociales": "VARCHAR",
    "considerationsEnvironnementales": "VARCHAR",
    "sousTraitanceDeclaree": "BOOLEAN",
    "lieuExecution_code": "VARCHAR",
    "lieuExecution_typeCode": "VARCHAR",
    "sourceDataset": "VARCHAR",
    "dureeMois": "SMALLINT",
    "offresRecues": "SMALLINT",
    "montant": "DOUBLE",
    "montant_rationalise": "DOUBLE",
    "montant_anomalie": "VARCHAR",
}

DEFAUT = {
    "donneesActuelles": True,
    "dateNotification": date(2024, 3, 1),
    "acheteur_id": "21350238800019",
    "acheteur_nom": "Commune de Rennes",
    "acheteur_departement_code": "35",
    "titulaire_typeIdentifiant": "SIRET",
    "titulaire_departement_code": "35",
    "objet": "Travaux de voirie",
    "codeCPV": "45233140-2",
    "nature": "Marché",
    "procedure": "Procédure adaptée",
    "dureeMois": 12,
    "offresRecues": 3,
    "montant_rationalise": 100_000.0,
}


def ecrire_parquet(chemin, lignes):
    """Écrit `lignes` (des dictionnaires partiels) dans un parquet au schéma DECP."""
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE t (" + ", ".join(f'"{c}" {t}' for c, t in COLONNES.items()) + ")"
    )
    for ligne in lignes:
        valeurs = {**DEFAUT, **ligne}
        valeurs.setdefault("montant", valeurs.get("montant_rationalise"))
        con.execute(
            "INSERT INTO t VALUES (" + ", ".join("?" for _ in COLONNES) + ")",
            [valeurs.get(c) for c in COLONNES],
        )
    cible = str(chemin).replace("'", "''")
    con.execute(f"COPY t TO '{cible}' (FORMAT parquet)")
    con.close()
    return chemin


@pytest.fixture
def fichier(tmp_path):
    """Fabrique un parquet à partir de lignes et rend son chemin."""
    compteur = iter(range(1000))

    def fabriquer(lignes):
        return ecrire_parquet(tmp_path / f"decp-{next(compteur)}.parquet", lignes)

    return fabriquer
