"""python -m decp_lecture [fichier] [--depuis AAAA-MM-JJ] : le journal de lecture."""

import argparse
import sys

from .lecture import journal, ouvrir

LIBELLES = {
    "depuis": "Marchés notifiés depuis le",
    "lignes_lues": "Lignes lues",
    "versions_non_actuelles": "  écartées, versions antérieures (donneesActuelles faux ou vide)",
    "sans_date": "  écartées, sans date de notification",
    "avant_periode": "  écartées, notifiées avant la période",
    "sans_uid": "  écartées, sans identifiant de marché (uid)",
    "titulaires_repetes": "  écartées, titulaire répété dans un même marché",
    "lignes_retenues": "Lignes retenues (couples marché-titulaire)",
    "marches": "Marchés (uid distincts)",
    "marches_montant_fiable": "  dont au montant fiable",
    "premiere_notification": "Première notification",
    "derniere_notification": "Dernière notification",
}


def main(arguments=None):
    lecteur = argparse.ArgumentParser(prog="python -m decp_lecture", description=__doc__)
    lecteur.add_argument("fichier", nargs="?", help="decp.parquet ; sans fichier, celui du jour sur data.gouv.fr")
    lecteur.add_argument("--depuis", default="2022-01-01", help="date de notification la plus ancienne retenue")
    lecteur.add_argument("--sirene", help="stock Sirene des unités légales (parquet ou CSV), facultatif")
    options = lecteur.parse_args(arguments)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    con = ouvrir(options.fichier, depuis=options.depuis, sirene=options.sirene)
    con.execute("SET enable_progress_bar = false")
    for cle, valeur in journal(con).items():
        texte = f"{valeur:,}".replace(",", " ") if isinstance(valeur, int) else str(valeur)
        print(f"{LIBELLES.get(cle, cle)} : {texte}")


if __name__ == "__main__":
    main()
