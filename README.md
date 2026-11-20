# decp-lecture

Lire les données essentielles de la commande publique (DECP) consolidées sans se tromper. Les règles de lecture appliquées dans Temi, écrites en SQL pour DuckDB, avec une petite interface Python.

Le jeu lu est [« Données essentielles de la commande publique consolidées (format tabulaire) »](https://www.data.gouv.fr/datasets/608c055b35eb4e6ee20eb325/), consolidé par Colin Maudry ([decp.info](https://decp.info)) : un fichier parquet d'environ 280 Mo et 3,2 millions de lignes. C'est la meilleure porte d'entrée vers les marchés attribués en France, et il se lit facilement de travers. Une ligne n'est pas un marché, un montant n'est pas toujours fiable, un groupement apparaît plusieurs fois.

## Ce que donne la lecture

Sur le fichier du 2 août 2026, en quelques secondes :

```text
Marchés notifiés depuis le : 2022-01-01
Lignes lues : 3 210 905
  écartées, versions antérieures (donneesActuelles faux ou vide) : 1 132 765
  écartées, sans date de notification : 0
  écartées, notifiées avant la période : 617 338
  écartées, sans identifiant de marché (uid) : 6
  écartées, titulaire répété dans un même marché : 11 182
Lignes retenues (couples marché-titulaire) : 1 449 614
Marchés (uid distincts) : 1 192 502
  dont au montant fiable : 1 127 390
Première notification : 2022-01-01
Dernière notification : 2026-08-01
```

## Installer

```bash
pip install git+https://github.com/V08-ai/decp-lecture
```

Python 3.10 ou plus et DuckDB 1.1 ou plus, la seule dépendance.

## Utiliser

```python
import decp_lecture

chemin = decp_lecture.telecharger("donnees/")   # le fichier du jour, environ 280 Mo
con = decp_lecture.ouvrir(chemin)

con.sql("""
    SELECT cpv_division,
           count(*) AS marches,
           count(*) FILTER (WHERE montant_fiable) AS assiette,
           median(montant) FILTER (WHERE montant_fiable) AS montant_median
    FROM decp_marches
    WHERE acheteur_departement = '35' AND year(dateNotification) = 2025
    GROUP BY cpv_division
    ORDER BY marches DESC
    LIMIT 5
""").show()
```

Les marchés notifiés en 2025 par les acheteurs d'Ille-et-Vilaine, par division CPV (fichier du 2 août 2026) :

| Division CPV | Marchés | dont au montant fiable | Montant médian |
|---|---:|---:|---:|
| 45 Travaux de construction | 2 785 | 2 657 | 87 569 € |
| 71 Services d'architecture et d'ingénierie | 680 | 649 | 51 870 € |
| 33 Matériel médical et pharmaceutique | 406 | 406 | 49 785 € |
| 90 Services d'assainissement et d'environnement | 258 | 245 | 76 000 € |
| 79 Services aux entreprises | 193 | 185 | 53 100 € |

`decp_lecture.ouvrir()` sans argument lit directement le fichier du jour sur data.gouv.fr, à distance. C'est pratique pour une requête, mais plus lent qu'un fichier local.

En ligne de commande, le journal de lecture :

```bash
python -m decp_lecture donnees/decp-2026-11-20.parquet
```

Sans Python, le SQL tient dans un fichier, [`regles.sql`](src/decp_lecture/regles.sql), qui se charge dans DuckDB après trois lignes de préparation :

```sql
CREATE VIEW decp_brut AS SELECT * FROM read_parquet('decp.parquet', file_row_number = true);
CREATE TABLE decp_sirene (siren VARCHAR, categorie_juridique VARCHAR);
CREATE MACRO decp_depuis() AS DATE '2022-01-01';
.read src/decp_lecture/regles.sql
```

## Les vues

| Vue | Une ligne par | Sert à |
|---|---|---|
| `decp_lignes` | couple marché-titulaire retenu | tout : colonnes d'origine et colonnes dérivées |
| `decp_marches` | marché (`uid`) | compter les marchés, calculer des montants |
| `decp_titulaires` | couple marché-titulaire, prêt à publier | classer les titulaires, partager les montants |
| `decp_journal` | une seule ligne | dire ce qui a été lu, écarté et retenu |

Colonnes ajoutées : `acheteur_departement`, `titulaire_departement`, `cpv_division`, `titulaire_siren`, `titulaire_personne_morale`, `nb_titulaires`, `montant`, `montant_fiable`, `montant_part`. Les autres gardent leur nom d'origine.

## Les règles

**1. Une ligne n'est pas un marché.**
- Seules les lignes `donneesActuelles` vrai comptent. Les autres, fausses ou vides, sont les versions antérieures d'un marché modifié.
- Un marché, c'est un `uid`. Compter des marchés, c'est compter des `uid` distincts. Une ligne sans `uid` est écartée.
- Un titulaire répété dans un même marché ne compte qu'une fois.
- Les attributs du marché se lisent une fois par `uid` : le plus grand nombre d'offres reçues, la plus longue durée, la plus ancienne date de notification, le premier montant renseigné (avec l'anomalie de la même ligne), la première valeur non vide pour le reste. « Premier » veut dire : dans l'ordre du fichier.

**2. Le montant : `montant_rationalise`, et seulement s'il est fiable.**
- Le montant brut, `montant`, n'est jamais lu.
- Un montant est fiable s'il est strictement positif et sans anomalie signalée. Dans le fichier, l'absence d'anomalie se lit comme un `montant_anomalie` vide ; les seules valeurs présentes sont `suspect` et `aberrant`.
- Les statistiques de montants (médiane, déciles, totaux) portent sur les seuls montants fiables et doivent dire leur assiette : « sur N marchés au montant fiable ». Les dénombrements (nombre de marchés, part des PME, part des offres uniques) portent sur tous les marchés.

**3. Les groupements : un partage à parts égales.** Le jeu ne dit pas comment le montant se répartit entre cotraitants. `montant_part` divise le montant du marché par le nombre de titulaires. C'est une convention, pas une donnée : elle garantit seulement que la somme des parts égale le montant du marché.

**4. Les titulaires qui sont des personnes.** Un titulaire n'est traité comme une personne morale que sur preuve : sa catégorie juridique Sirene (1000 = entrepreneur individuel), sinon une forme juridique dans son nom (SAS, SARL, association, commune…). Dans le doute, c'est une personne. Elle compte dans tous les totaux, mais `decp_titulaires` retire son nom, ses identifiants et son département.

Sans fichier Sirene, la règle est très prudente : 88 % des lignes sont traitées comme des personnes, faute de forme juridique dans le nom. Pour reconnaître les sociétés, chargez le stock des unités légales de la [base Sirene](https://www.data.gouv.fr/datasets/5b7ffc618b4c4169d30727e0/) (fichier `StockUniteLegale` au format parquet, dont seules deux colonnes sont lues) :

```python
con = decp_lecture.ouvrir(chemin, sirene="StockUniteLegale.parquet")
```

**5. Les nettoyages.**
- Les codes département : « 6 » ou « 006 » deviennent « 06 », la Corse garde 2A et 2B, l'outre-mer ses trois chiffres. Un code invalide est mis à vide, la ligne reste.
- La division CPV : les deux premiers caractères de `codeCPV`, parmi les 45 divisions de la nomenclature de 2008. Une division hors nomenclature est mise à vide.
- Les lignes sans date de notification sont écartées, et comptées.
- La période : par défaut, les marchés notifiés depuis le 1er janvier 2022, à partir duquel la couverture devient assez régulière. Le paramètre `depuis` la change.

**6. L'adresse du fichier.** Elle change à chaque mise à jour. `adresse_parquet()` la demande à l'API de data.gouv.fr à chaque lecture, plutôt que de la figer dans le code.

## Ce que les règles ne règlent pas

- **Un `uid` peut porter des montants différents.** Sur le fichier du 2 août 2026, 15 307 marchés (1,3 %) ont des lignes aux montants différents : un même identifiant sert à plusieurs lots, ou à plusieurs marchés du même acheteur. Le premier montant est retenu. Pour une analyse fine d'un acheteur, regardez `decp_lignes`.
- **Les montants à 0 € ne sont pas signalés comme anomalies.** 22 077 marchés sont déclarés à 0 € (ou moins) sans anomalie. Ils comptent dans les dénombrements, pas dans les montants. Les garder ferait passer le montant médian national de 118 950 € à 113 700 €.
- **Le partage à parts égales est une convention.** La répartition réelle entre cotraitants peut être très inégale ; la source ne la donne pas.

## Vérifier

```bash
python -m pytest
```

Les tests fabriquent de petits fichiers au schéma du vrai, une règle à la fois. Sur un vrai fichier, d'autres tests contrôlent les invariants : le journal tombe juste, un marché par `uid`, des parts qui égalent le montant, aucune personne nommée.

```bash
DECP_PARQUET=donnees/decp.parquet python -m pytest tests/test_fichier_reel.py
```

## Citer la source

« Données essentielles de la commande publique, consolidation Colin Maudry (decp.info), data.gouv.fr, Licence Ouverte 2.0 ». Les données ne sont pas distribuées avec ce code.

## Licence

Code sous [licence Apache 2.0](LICENSE). Copyright 2026 Temi.

Écrit par Victor Lavolé pour [Temi](https://temiapp.com), qui aide les entreprises à répondre aux marchés publics.
