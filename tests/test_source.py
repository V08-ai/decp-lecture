import pytest

from decp_lecture import choisir_ressource

RESSOURCES = [
    {"id": "a", "title": "statistiques-doublons-sources.parquet", "format": "parquet", "url": "https://x/doublons.parquet"},
    {"id": "b", "title": "decp.csv.gz", "format": "csv.gz", "url": "https://x/decp.csv.gz"},
    {"id": "c", "title": "decp.parquet", "format": "parquet", "url": "https://x/20261120/decp.parquet",
     "last_modified": "2026-11-20T05:11:52+00:00", "filesize": 277344551},
]


def test_le_fichier_principal_et_pas_les_annexes():
    ressource = choisir_ressource(RESSOURCES)
    assert ressource == {
        "id": "c",
        "titre": "decp.parquet",
        "url": "https://x/20261120/decp.parquet",
        "derniere_maj": "2026-11-20T05:11:52+00:00",
        "taille": 277344551,
    }


def test_un_titre_qui_change_un_peu():
    ressource = choisir_ressource([RESSOURCES[0], {**RESSOURCES[2], "title": "DECP consolidées (parquet)"}])
    assert ressource["id"] == "c"


def test_aucun_parquet():
    with pytest.raises(LookupError):
        choisir_ressource(RESSOURCES[:2][1:])
