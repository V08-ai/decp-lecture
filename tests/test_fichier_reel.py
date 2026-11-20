"""Les invariants des règles sur un vrai decp.parquet.

Ces tests ne tournent que si la variable DECP_PARQUET désigne un fichier :

    DECP_PARQUET=decp.parquet python -m pytest tests/test_fichier_reel.py
"""

import os

import pytest

from decp_lecture import journal, ouvrir

CHEMIN = os.environ.get("DECP_PARQUET")
pytestmark = pytest.mark.skipif(not CHEMIN, reason="DECP_PARQUET non défini")


@pytest.fixture(scope="module")
def con():
    return ouvrir(CHEMIN)


def valeur(con, sql):
    return con.execute(sql).fetchone()[0]


def test_le_journal_tombe_juste(con):
    j = journal(con)
    ecartees = j["versions_non_actuelles"] + j["sans_date"] + j["avant_periode"] + j["sans_uid"] + j["titulaires_repetes"]
    assert j["lignes_lues"] == ecartees + j["lignes_retenues"]


def test_un_marche_par_uid(con):
    assert valeur(con, "SELECT count(*) - count(DISTINCT uid) FROM decp_marches") == 0


def test_un_titulaire_par_marche(con):
    assert valeur(con, "SELECT sum(nb_titulaires) FROM decp_marches") == valeur(con, "SELECT count(*) FROM decp_lignes")


def test_les_parts_ne_depassent_jamais_le_marche(con):
    ecart = valeur(con, """
        SELECT max(abs(t.total - m.montant) / m.montant)
        FROM (SELECT uid, sum(montant_part) AS total FROM decp_titulaires GROUP BY uid) AS t
        JOIN decp_marches AS m USING (uid)
        WHERE m.montant_fiable
    """)
    assert ecart < 1e-9


def test_aucun_montant_fiable_douteux(con):
    assert valeur(con, """
        SELECT count(*) FROM decp_marches
        WHERE montant_fiable AND (montant IS NULL OR montant <= 0 OR montant_anomalie IS NOT NULL)
    """) == 0


def test_aucune_personne_nommee(con):
    assert valeur(con, """
        SELECT count(*) FROM decp_titulaires
        WHERE NOT titulaire_personne_morale
          AND (titulaire_nom IS NOT NULL OR titulaire_id IS NOT NULL OR titulaire_departement IS NOT NULL)
    """) == 0


def test_codes_propres(con):
    assert valeur(con, """
        SELECT count(*) FROM decp_lignes
        WHERE NOT list_contains(decp_departements_valides(), acheteur_departement)
           OR NOT list_contains(decp_divisions_cpv(), cpv_division)
    """) == 0
