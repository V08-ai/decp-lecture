"""Ouvrir les DECP consolidées dans DuckDB, avec les règles de lecture appliquées."""

from __future__ import annotations

import json
import shutil
import urllib.request
from datetime import date
from importlib.resources import files
from pathlib import Path
from typing import Optional, Union

import duckdb

JEU_DECP = "608c055b35eb4e6ee20eb325"
"""Le jeu « Données essentielles de la commande publique consolidées (format tabulaire) »."""

API_DATAGOUV = "https://www.data.gouv.fr/api/1/datasets/{}/"
AGENT = "decp-lecture (https://github.com/V08-ai/decp-lecture)"

REGLES = files("decp_lecture").joinpath("regles.sql").read_text(encoding="utf-8")
"""Le SQL des règles : macros et vues decp_lignes, decp_marches, decp_titulaires, decp_journal."""

Chemin = Union[str, Path]


def adresse_parquet(*, delai: float = 30) -> dict:
    """L'adresse du fichier decp.parquet du jour, demandée à l'API de data.gouv.fr.

    L'adresse change à chaque mise à jour : on la demande à chaque lecture plutôt
    que de la figer. Rend `{"id", "titre", "url", "derniere_maj", "taille"}`.
    """
    requete = urllib.request.Request(
        API_DATAGOUV.format(JEU_DECP),
        headers={"Accept": "application/json", "User-Agent": AGENT},
    )
    with urllib.request.urlopen(requete, timeout=delai) as reponse:
        jeu = json.load(reponse)
    return choisir_ressource(jeu.get("resources", []))


def choisir_ressource(ressources: list[dict]) -> dict:
    """Parmi les ressources du jeu, le fichier parquet principal (pas les annexes)."""
    parquets = [r for r in ressources if (r.get("format") or "").lower() == "parquet"]
    for critere in (
        lambda titre: titre == "decp.parquet",
        lambda titre: "decp" in titre,
    ):
        for r in parquets:
            if critere((r.get("title") or "").lower()):
                return {
                    "id": r.get("id"),
                    "titre": r.get("title"),
                    "url": r.get("url"),
                    "derniere_maj": r.get("last_modified"),
                    "taille": r.get("filesize"),
                }
    raise LookupError(f"aucun fichier decp.parquet parmi les ressources du jeu {JEU_DECP}")


def telecharger(dossier: Chemin = ".", *, delai: float = 60) -> Path:
    """Télécharge le decp.parquet du jour dans `dossier` et rend son chemin.

    Le fichier pèse environ 280 Mo. Le lire en local est bien plus rapide que de
    l'interroger à distance à chaque requête.
    """
    ressource = adresse_parquet(delai=delai)
    jour = (ressource["derniere_maj"] or "")[:10] or date.today().isoformat()
    Path(dossier).mkdir(parents=True, exist_ok=True)
    cible = Path(dossier) / f"decp-{jour}.parquet"
    partiel = cible.with_suffix(".parquet.partiel")
    requete = urllib.request.Request(ressource["url"], headers={"User-Agent": AGENT})
    with urllib.request.urlopen(requete, timeout=delai) as reponse, open(partiel, "wb") as sortie:
        shutil.copyfileobj(reponse, sortie, length=1 << 20)
    partiel.replace(cible)
    return cible


def ouvrir(
    source: Optional[Chemin] = None,
    *,
    depuis: Union[str, date] = "2022-01-01",
    sirene: Optional[Chemin] = None,
    connexion: Optional[duckdb.DuckDBPyConnection] = None,
) -> duckdb.DuckDBPyConnection:
    """Une connexion DuckDB où les règles de lecture sont déjà appliquées.

    `source` : un chemin ou une adresse vers decp.parquet. Sans source, l'adresse
    du jour est demandée à data.gouv.fr et le fichier est lu à distance.
    `depuis` : la date de notification la plus ancienne retenue.
    `sirene` : facultatif, le stock des unités légales Sirene (parquet ou CSV,
    colonnes `siren` et `categorieJuridiqueUniteLegale`), pour reconnaître les
    entrepreneurs individuels par leur catégorie juridique plutôt que par leur nom.

    La connexion expose les vues `decp_lignes`, `decp_marches`, `decp_titulaires`
    et `decp_journal`.
    """
    con = connexion if connexion is not None else duckdb.connect()
    if source is None:
        source = adresse_parquet()["url"]
    debut = depuis if isinstance(depuis, date) else date.fromisoformat(str(depuis))

    con.execute(
        "CREATE OR REPLACE VIEW decp_brut AS "
        f"SELECT * FROM read_parquet({_litteral(source)}, file_row_number = true)"
    )
    con.execute(f"CREATE OR REPLACE MACRO decp_depuis() AS DATE {_litteral(debut.isoformat())}")
    con.execute("CREATE OR REPLACE TABLE decp_sirene (siren VARCHAR, categorie_juridique VARCHAR)")
    con.execute(REGLES)
    if sirene is not None:
        charger_sirene(con, sirene)
    return con


def charger_sirene(con: duckdb.DuckDBPyConnection, chemin: Chemin) -> int:
    """Charge les catégories juridiques Sirene des seuls titulaires du fichier DECP.

    Rend le nombre d'unités légales chargées.
    """
    texte = str(chemin)
    lecteur = (
        f"read_parquet({_litteral(texte)})"
        if texte.lower().endswith(".parquet")
        else f"read_csv({_litteral(texte)}, all_varchar = true)"
    )
    con.execute(
        f"""
        INSERT INTO decp_sirene
        SELECT CAST(siren AS VARCHAR), any_value(CAST(categorieJuridiqueUniteLegale AS VARCHAR))
        FROM {lecteur}
        WHERE CAST(siren AS VARCHAR) IN (
            SELECT DISTINCT decp_siren(titulaire_id, titulaire_typeIdentifiant) FROM decp_brut
        )
        GROUP BY 1
        """
    )
    return con.execute("SELECT count(*) FROM decp_sirene").fetchone()[0]


def journal(con: duckdb.DuckDBPyConnection) -> dict:
    """Ce qui a été lu, écarté et retenu, sous forme de dictionnaire."""
    curseur = con.execute("SELECT * FROM decp_journal")
    noms = [colonne[0] for colonne in curseur.description]
    return dict(zip(noms, curseur.fetchone()))


def _litteral(valeur: Chemin) -> str:
    """Une chaîne SQL entre apostrophes, apostrophes internes doublées."""
    return "'" + str(valeur).replace("'", "''") + "'"
