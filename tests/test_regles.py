from datetime import date

import duckdb
import pytest

from decp_lecture import journal, ouvrir

SIRET_SAS = "55210055400013"
SIRET_PERSONNE = "81234567800011"
SIRET_AUTRE = "41234567800019"


def valeur(con, sql, *parametres):
    return con.execute(sql, list(parametres)).fetchone()[0]


# 1. Une ligne n'est pas un marché


def test_seules_les_versions_actuelles_comptent(fichier):
    con = ouvrir(fichier([
        {"uid": "M1", "titulaire_id": SIRET_SAS, "montant_rationalise": 90_000.0, "donneesActuelles": False},
        {"uid": "M1", "titulaire_id": SIRET_SAS, "montant_rationalise": 120_000.0},
        {"uid": "M2", "titulaire_id": SIRET_SAS, "donneesActuelles": None},
    ]))
    assert valeur(con, "SELECT count(*) FROM decp_marches") == 1
    assert valeur(con, "SELECT montant FROM decp_marches WHERE uid = 'M1'") == 120_000.0
    assert journal(con)["versions_non_actuelles"] == 2


def test_un_groupement_est_un_seul_marche(fichier):
    con = ouvrir(fichier([
        {"uid": "M1", "titulaire_id": SIRET_SAS, "titulaire_nom": "BTP OUEST SAS"},
        {"uid": "M1", "titulaire_id": SIRET_AUTRE, "titulaire_nom": "TERRASSEMENTS SARL"},
    ]))
    assert valeur(con, "SELECT count(*) FROM decp_lignes") == 2
    assert valeur(con, "SELECT count(*) FROM decp_marches") == 1
    assert valeur(con, "SELECT nb_titulaires FROM decp_marches") == 2


def test_un_titulaire_repete_ne_compte_qu_une_fois(fichier):
    con = ouvrir(fichier([
        {"uid": "M1", "titulaire_id": SIRET_SAS},
        {"uid": "M1", "titulaire_id": SIRET_SAS},
        {"uid": "M1", "titulaire_id": SIRET_AUTRE},
    ]))
    assert valeur(con, "SELECT nb_titulaires FROM decp_marches") == 2
    assert journal(con)["titulaires_repetes"] == 1


def test_titulaires_sans_identifiant_distingues_par_leur_nom(fichier):
    con = ouvrir(fichier([
        {"uid": "M1", "titulaire_id": None, "titulaire_nom": "ALPHA SAS"},
        {"uid": "M1", "titulaire_id": None, "titulaire_nom": "BETA SAS"},
    ]))
    assert valeur(con, "SELECT nb_titulaires FROM decp_marches") == 2


def test_attributs_lus_une_fois_par_marche(fichier):
    con = ouvrir(fichier([
        {"uid": "M1", "titulaire_id": SIRET_SAS, "offresRecues": 2, "objet": "", "ccag": None,
         "montant_rationalise": None, "dateNotification": date(2024, 5, 1)},
        {"uid": "M1", "titulaire_id": SIRET_AUTRE, "offresRecues": 5, "objet": "Voirie",
         "ccag": "Travaux", "montant_rationalise": 80_000.0, "dateNotification": date(2024, 4, 1)},
    ]))
    ligne = con.execute(
        "SELECT offresRecues, objet, ccag, montant, dateNotification FROM decp_marches"
    ).fetchone()
    # Le plus grand nombre d'offres, le premier objet non vide, le premier
    # montant renseigné, la plus ancienne date de notification.
    assert ligne == (5, "Voirie", "Travaux", 80_000.0, date(2024, 4, 1))


# 2. Le montant : montant_rationalise, et seulement s'il est fiable


@pytest.mark.parametrize(
    "montant, anomalie, fiable",
    [
        (50_000.0, None, True),
        (50_000.0, "", True),
        (50_000.0, "suspect", False),
        (50_000.0, "aberrant", False),
        (0.0, None, False),
        (-10.0, None, False),
        (None, None, False),
    ],
)
def test_montant_fiable(fichier, montant, anomalie, fiable):
    con = ouvrir(fichier([
        {"uid": "M1", "titulaire_id": SIRET_SAS, "montant_rationalise": montant, "montant_anomalie": anomalie},
    ]))
    assert valeur(con, "SELECT montant_fiable FROM decp_marches") is fiable


def test_le_montant_brut_n_est_jamais_lu(fichier):
    con = ouvrir(fichier([
        {"uid": "M1", "titulaire_id": SIRET_SAS, "montant": 9e12, "montant_rationalise": 120_000.0},
    ]))
    assert valeur(con, "SELECT montant FROM decp_marches") == 120_000.0


def test_l_anomalie_est_celle_du_montant_retenu(fichier):
    con = ouvrir(fichier([
        {"uid": "M1", "titulaire_id": SIRET_SAS, "montant_rationalise": 70_000.0, "montant_anomalie": "suspect"},
        {"uid": "M1", "titulaire_id": SIRET_AUTRE, "montant_rationalise": 70_000.0, "montant_anomalie": None},
    ]))
    assert con.execute("SELECT montant_anomalie, montant_fiable FROM decp_marches").fetchone() == ("suspect", False)


# 3. Les groupements : un partage à parts égales


def test_partage_a_parts_egales(fichier):
    con = ouvrir(fichier([
        {"uid": "M1", "titulaire_id": SIRET_SAS, "titulaire_nom": "A SAS", "montant_rationalise": 90_000.0},
        {"uid": "M1", "titulaire_id": SIRET_AUTRE, "titulaire_nom": "B SAS", "montant_rationalise": 90_000.0},
        {"uid": "M1", "titulaire_id": "40000000000001", "titulaire_nom": "C SAS", "montant_rationalise": 90_000.0},
    ]))
    parts = [r[0] for r in con.execute("SELECT montant_part FROM decp_titulaires").fetchall()]
    assert parts == [30_000.0] * 3
    assert sum(parts) == valeur(con, "SELECT montant FROM decp_marches")


def test_pas_de_part_sans_montant_fiable(fichier):
    con = ouvrir(fichier([
        {"uid": "M1", "titulaire_id": SIRET_SAS, "titulaire_nom": "A SAS", "montant_anomalie": "aberrant"},
    ]))
    assert valeur(con, "SELECT montant_part FROM decp_titulaires") is None


# 4. Les titulaires qui sont des personnes


@pytest.mark.parametrize(
    "nom, personne_morale",
    [
        ("BTP OUEST SAS", True),
        ("Société Générale de Travaux", True),
        ("S.A.R.L. Dupont", True),
        ("Commune de Bais", True),
        ("Jean Martin", False),
        ("MARTIN Jean - Plomberie", False),
        ("", False),
        (None, False),
    ],
)
def test_personne_morale_sur_preuve_dans_le_nom(fichier, nom, personne_morale):
    con = ouvrir(fichier([{"uid": "M1", "titulaire_id": SIRET_PERSONNE, "titulaire_nom": nom}]))
    assert valeur(con, "SELECT titulaire_personne_morale FROM decp_lignes") is personne_morale


def test_la_categorie_sirene_prime_sur_le_nom(fichier, tmp_path):
    sirene = tmp_path / "StockUniteLegale.csv"
    sirene.write_text(
        "siren,categorieJuridiqueUniteLegale\n"
        f"{SIRET_PERSONNE[:9]},1000\n"
        f"{SIRET_AUTRE[:9]},5710\n"
        "999999999,5499\n",
        encoding="utf-8",
    )
    con = ouvrir(
        fichier([
            {"uid": "M1", "titulaire_id": SIRET_PERSONNE, "titulaire_nom": "DUPONT SAS"},
            {"uid": "M2", "titulaire_id": SIRET_AUTRE, "titulaire_nom": "QUALICONSULT"},
        ]),
        sirene=sirene,
    )
    lignes = dict(con.execute("SELECT uid, titulaire_personne_morale FROM decp_lignes").fetchall())
    # Entrepreneur individuel malgré « SAS » dans le nom ; société malgré l'absence de forme.
    assert lignes == {"M1": False, "M2": True}
    # Seuls les titulaires du fichier sont chargés.
    assert valeur(con, "SELECT count(*) FROM decp_sirene") == 2


def test_une_personne_compte_mais_n_est_ni_nommee_ni_localisee(fichier):
    con = ouvrir(fichier([
        {"uid": "M1", "titulaire_id": SIRET_SAS, "titulaire_nom": "BTP OUEST SAS", "montant_rationalise": 60_000.0},
        {"uid": "M1", "titulaire_id": SIRET_PERSONNE, "titulaire_nom": "Jean Martin", "montant_rationalise": 60_000.0},
    ]))
    lignes = con.execute(
        "SELECT titulaire_nom, titulaire_id, titulaire_siren, titulaire_departement, montant_part "
        "FROM decp_titulaires ORDER BY titulaire_nom NULLS LAST"
    ).fetchall()
    assert lignes == [
        ("BTP OUEST SAS", SIRET_SAS, SIRET_SAS[:9], "35", 30_000.0),
        (None, None, None, None, 30_000.0),
    ]
    # Un groupement n'est « entre personnes morales » que si tous ses membres le sont.
    assert valeur(con, "SELECT titulaires_personnes_morales FROM decp_marches") is False


# 5. Les nettoyages


@pytest.mark.parametrize(
    "brut, attendu",
    [
        ("35", "35"), ("6", "06"), ("006", "06"), ("093", "93"), (" 2a ", "2A"), ("2B", "2B"),
        ("971", "971"), ("988", "988"), ("20", None), ("00", None), ("99", None), ("980", None),
        ("Ille-et-Vilaine", None), (None, None),
    ],
)
def test_codes_departement(fichier, brut, attendu):
    con = ouvrir(fichier([{"uid": "M1", "titulaire_id": SIRET_SAS, "acheteur_departement_code": brut}]))
    assert valeur(con, "SELECT acheteur_departement FROM decp_lignes") == attendu
    assert valeur(con, "SELECT count(*) FROM decp_lignes") == 1


@pytest.mark.parametrize(
    "code, division",
    [("45233140-2", "45"), (" 71000000", "71"), ("03000000-1", "03"), ("00000000", None),
     ("99999999", None), ("Travaux", None), (None, None)],
)
def test_division_cpv(fichier, code, division):
    con = ouvrir(fichier([{"uid": "M1", "titulaire_id": SIRET_SAS, "codeCPV": code}]))
    assert valeur(con, "SELECT cpv_division FROM decp_lignes") == division


@pytest.mark.parametrize(
    "identifiant, type_id, siren",
    [(SIRET_SAS, "SIRET", SIRET_SAS[:9]), ("552 100 554 00013", "siret", "552100554"),
     ("FR40303265045", "TVA", None), ("1234", "SIRET", None), (None, "SIRET", None)],
)
def test_siren_du_titulaire(fichier, identifiant, type_id, siren):
    con = ouvrir(fichier([{"uid": "M1", "titulaire_id": identifiant, "titulaire_typeIdentifiant": type_id}]))
    assert valeur(con, "SELECT titulaire_siren FROM decp_lignes") == siren


def test_periode_dates_et_uid(fichier):
    chemin = fichier([
        {"uid": "M1", "titulaire_id": SIRET_SAS, "dateNotification": date(2021, 12, 31)},
        {"uid": "M2", "titulaire_id": SIRET_SAS, "dateNotification": date(2022, 1, 1)},
        {"uid": "M3", "titulaire_id": SIRET_SAS, "dateNotification": None},
        {"uid": None, "titulaire_id": SIRET_SAS},
        {"uid": "M4", "titulaire_id": SIRET_SAS, "dateNotification": date(2025, 6, 1)},
    ])
    con = ouvrir(chemin)
    assert [r[0] for r in con.execute("SELECT uid FROM decp_marches ORDER BY uid").fetchall()] == ["M2", "M4"]
    j = journal(con)
    assert (j["lignes_lues"], j["avant_periode"], j["sans_date"], j["sans_uid"], j["marches"]) == (5, 1, 1, 1, 2)
    assert journal(ouvrir(chemin, depuis="2025-01-01"))["marches"] == 1


def test_le_journal_tombe_juste(fichier):
    con = ouvrir(fichier([
        {"uid": "M1", "titulaire_id": SIRET_SAS, "donneesActuelles": False},
        {"uid": "M1", "titulaire_id": SIRET_SAS},
        {"uid": "M1", "titulaire_id": SIRET_SAS},
        {"uid": "M2", "titulaire_id": SIRET_SAS, "dateNotification": date(2020, 1, 1)},
        {"uid": "M3", "titulaire_id": SIRET_SAS, "montant_anomalie": "suspect"},
    ]))
    j = journal(con)
    ecartees = j["versions_non_actuelles"] + j["sans_date"] + j["avant_periode"] + j["sans_uid"] + j["titulaires_repetes"]
    assert j["lignes_lues"] == ecartees + j["lignes_retenues"]
    assert (j["marches"], j["marches_montant_fiable"]) == (2, 1)


def test_une_connexion_existante(fichier):
    con = duckdb.connect()
    assert ouvrir(fichier([{"uid": "M1", "titulaire_id": SIRET_SAS}]), connexion=con) is con
    assert valeur(con, "SELECT count(*) FROM decp_marches") == 1


def test_un_chemin_avec_une_apostrophe(tmp_path):
    from conftest import ecrire_parquet

    dossier = tmp_path / "l'export"
    dossier.mkdir()
    con = ouvrir(ecrire_parquet(dossier / "decp.parquet", [{"uid": "M1", "titulaire_id": SIRET_SAS}]))
    assert valeur(con, "SELECT count(*) FROM decp_marches") == 1
