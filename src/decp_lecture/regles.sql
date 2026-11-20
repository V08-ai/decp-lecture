-- decp-lecture : les règles de lecture des DECP consolidées, en SQL DuckDB.
--
-- Ce fichier attend trois choses, que la fonction Python `ouvrir` prépare :
--
--   CREATE VIEW decp_brut AS
--     SELECT * FROM read_parquet('decp.parquet', file_row_number = true);
--   CREATE TABLE decp_sirene (siren VARCHAR, categorie_juridique VARCHAR);  -- peut rester vide
--   CREATE MACRO decp_depuis() AS DATE '2022-01-01';
--
-- Il crée quatre vues : decp_lignes, decp_marches, decp_titulaires, decp_journal.
-- « Premier » veut toujours dire : dans l'ordre du fichier (file_row_number).


-- Référentiels ----------------------------------------------------------------

-- Départements : métropole 01 à 95 (le 20 n'existe plus), Corse 2A et 2B,
-- outre-mer où des marchés sont passés.
CREATE OR REPLACE MACRO decp_departements_valides() AS [
    '01', '02', '03', '04', '05', '06', '07', '08', '09', '10', '11', '12', '13', '14', '15',
    '16', '17', '18', '19', '2A', '2B', '21', '22', '23', '24', '25', '26', '27', '28', '29',
    '30', '31', '32', '33', '34', '35', '36', '37', '38', '39', '40', '41', '42', '43', '44',
    '45', '46', '47', '48', '49', '50', '51', '52', '53', '54', '55', '56', '57', '58', '59',
    '60', '61', '62', '63', '64', '65', '66', '67', '68', '69', '70', '71', '72', '73', '74',
    '75', '76', '77', '78', '79', '80', '81', '82', '83', '84', '85', '86', '87', '88', '89',
    '90', '91', '92', '93', '94', '95', '971', '972', '973', '974', '975', '976', '977', '978', '984',
    '986', '987', '988'
];

-- « 6 » et « 006 » deviennent « 06 », « 2a » devient « 2A ».
CREATE OR REPLACE MACRO decp_departement_candidat(v) AS CASE
    WHEN regexp_full_match(v, '[0-9]') THEN '0' || v
    WHEN regexp_full_match(v, '0[0-9]{2}') THEN substr(v, 2)
    ELSE v
END;

-- Un code hors référentiel devient NULL ; la ligne reste.
CREATE OR REPLACE MACRO decp_departement(code) AS CASE
    WHEN list_contains(decp_departements_valides(),
                       decp_departement_candidat(upper(trim(CAST(code AS VARCHAR)))))
    THEN decp_departement_candidat(upper(trim(CAST(code AS VARCHAR))))
END;

-- Les 45 divisions de la nomenclature CPV 2008.
CREATE OR REPLACE MACRO decp_divisions_cpv() AS [
    '03', '09', '14', '15', '16', '18', '19', '22', '24', '30', '31', '32', '33', '34', '35',
    '37', '38', '39', '41', '42', '43', '44', '45', '48', '50', '51', '55', '60', '63', '64',
    '65', '66', '70', '71', '72', '73', '75', '76', '77', '79', '80', '85', '90', '92', '98'
];

-- La division : les deux premiers caractères du code CPV, NULL hors nomenclature.
CREATE OR REPLACE MACRO decp_division_cpv(code) AS CASE
    WHEN list_contains(decp_divisions_cpv(), left(trim(CAST(code AS VARCHAR)), 2))
    THEN left(trim(CAST(code AS VARCHAR)), 2)
END;

-- Le SIREN d'un titulaire identifié par un SIRET valide (14 chiffres).
CREATE OR REPLACE MACRO decp_siren(id, type_id) AS CASE
    WHEN upper(trim(CAST(type_id AS VARCHAR))) = 'SIRET'
     AND regexp_full_match(regexp_replace(CAST(id AS VARCHAR), '\s', '', 'g'), '[0-9]{14}')
    THEN left(regexp_replace(CAST(id AS VARCHAR), '\s', '', 'g'), 9)
END;

-- Les mots qui prouvent une personne morale : formes juridiques, entités publiques.
-- Une personne physique ne les porte pas dans son nom.
CREATE OR REPLACE MACRO decp_marqueurs_personne_morale() AS [
    'SARL', 'SAS', 'SASU', 'EURL', 'SA', 'SNC', 'SCA', 'SCS', 'SCOP', 'SCIC', 'SCM', 'SCP',
    'SEL', 'SELARL', 'SELAS', 'SELAFA', 'SELCA', 'SCI', 'SEM', 'SEML', 'SPL', 'SPLA', 'SAEM',
    'EPIC', 'EPA', 'EPCI', 'GIE', 'GEIE', 'GAEC', 'EARL', 'SCEA', 'ASSOCIATION', 'FONDATION',
    'MUTUELLE', 'COOPERATIVE', 'SYNDICAT', 'FEDERATION', 'GROUPEMENT', 'COMMUNE', 'DEPARTEMENT',
    'REGION', 'METROPOLE', 'CCAS', 'CIAS', 'SDIS', 'CHU', 'CHR', 'CHRU', 'UNIVERSITE', 'OFFICE',
    'OPH', 'OPHLM', 'ETABLISSEMENT', 'SOCIETE', 'GMBH', 'LTD', 'INC', 'PLC'
];

-- Les points sont retirés avant de découper le nom en mots : « S.A.R.L. » se lit « SARL ».
CREATE OR REPLACE MACRO decp_nom_de_personne_morale(nom) AS coalesce(list_has_any(
    string_split(trim(regexp_replace(
        replace(upper(strip_accents(CAST(nom AS VARCHAR))), '.', ''), '[^A-Z0-9]+', ' ', 'g')), ' '),
    decp_marqueurs_personne_morale()
), false);


-- 1. Les lignes : un couple marché-titulaire, version actuelle, notifié dans la période.

CREATE OR REPLACE VIEW decp_lignes AS
WITH retenues AS (
    SELECT *
    FROM decp_brut
    WHERE TRY_CAST(donneesActuelles AS BOOLEAN) IS TRUE
      AND TRY_CAST(dateNotification AS DATE) >= decp_depuis()
      AND nullif(trim(uid), '') IS NOT NULL
),
uniques AS (
    -- Un même titulaire répété dans un marché ne compte qu'une fois.
    SELECT *
    FROM retenues
    QUALIFY row_number() OVER (
        PARTITION BY uid, coalesce(titulaire_id, titulaire_nom, CAST(file_row_number AS VARCHAR))
        ORDER BY file_row_number
    ) = 1
)
SELECT
    u.*,
    decp_departement(u.acheteur_departement_code) AS acheteur_departement,
    decp_departement(u.titulaire_departement_code) AS titulaire_departement,
    decp_division_cpv(u.codeCPV) AS cpv_division,
    decp_siren(u.titulaire_id, u.titulaire_typeIdentifiant) AS titulaire_siren,
    -- Personne morale seulement sur preuve : la catégorie juridique Sirene d'abord
    -- (1000 = entrepreneur individuel), sinon une forme juridique dans le nom.
    -- Dans le doute, le titulaire est traité comme une personne physique.
    CASE
        WHEN s.categorie_juridique LIKE '1%' THEN false
        WHEN nullif(trim(s.categorie_juridique), '') IS NOT NULL THEN true
        ELSE decp_nom_de_personne_morale(u.titulaire_nom)
    END AS titulaire_personne_morale,
    count(*) OVER (PARTITION BY u.uid) AS nb_titulaires
FROM uniques AS u
LEFT JOIN decp_sirene AS s
    ON s.siren = decp_siren(u.titulaire_id, u.titulaire_typeIdentifiant);


-- 2. Les marchés : une ligne par uid, ses attributs lus une fois.

CREATE OR REPLACE VIEW decp_marches AS
WITH m AS (
    SELECT
        uid,
        min(file_row_number) AS premiere_ligne,
        arg_min(acheteur_id, file_row_number) FILTER (WHERE nullif(trim(acheteur_id), '') IS NOT NULL) AS acheteur_id,
        arg_min(acheteur_nom, file_row_number) FILTER (WHERE nullif(trim(acheteur_nom), '') IS NOT NULL) AS acheteur_nom,
        arg_min(acheteur_departement, file_row_number) FILTER (WHERE acheteur_departement IS NOT NULL) AS acheteur_departement,
        arg_min(objet, file_row_number) FILTER (WHERE nullif(trim(objet), '') IS NOT NULL) AS objet,
        arg_min(codeCPV, file_row_number) FILTER (WHERE nullif(trim(codeCPV), '') IS NOT NULL) AS codeCPV,
        arg_min(cpv_division, file_row_number) FILTER (WHERE cpv_division IS NOT NULL) AS cpv_division,
        arg_min(nature, file_row_number) FILTER (WHERE nullif(trim(nature), '') IS NOT NULL) AS nature,
        arg_min("procedure", file_row_number) FILTER (WHERE nullif(trim("procedure"), '') IS NOT NULL) AS "procedure",
        arg_min(formePrix, file_row_number) FILTER (WHERE nullif(trim(formePrix), '') IS NOT NULL) AS formePrix,
        arg_min(ccag, file_row_number) FILTER (WHERE nullif(trim(ccag), '') IS NOT NULL) AS ccag,
        arg_min(typeGroupementOperateurs, file_row_number) FILTER (WHERE nullif(trim(typeGroupementOperateurs), '') IS NOT NULL) AS typeGroupementOperateurs,
        arg_min(considerationsSociales, file_row_number) FILTER (WHERE nullif(trim(considerationsSociales), '') IS NOT NULL) AS considerationsSociales,
        arg_min(considerationsEnvironnementales, file_row_number) FILTER (WHERE nullif(trim(considerationsEnvironnementales), '') IS NOT NULL) AS considerationsEnvironnementales,
        arg_min(sousTraitanceDeclaree, file_row_number) FILTER (WHERE sousTraitanceDeclaree IS NOT NULL) AS sousTraitanceDeclaree,
        arg_min(lieuExecution_code, file_row_number) FILTER (WHERE nullif(trim(lieuExecution_code), '') IS NOT NULL) AS lieuExecution_code,
        arg_min(lieuExecution_typeCode, file_row_number) FILTER (WHERE nullif(trim(lieuExecution_typeCode), '') IS NOT NULL) AS lieuExecution_typeCode,
        arg_min(sourceDataset, file_row_number) FILTER (WHERE nullif(trim(sourceDataset), '') IS NOT NULL) AS sourceDataset,
        min(TRY_CAST(dateNotification AS DATE)) AS dateNotification,
        max(dureeMois) AS dureeMois,
        max(offresRecues) AS offresRecues,
        -- Le premier montant renseigné, avec l'anomalie de la même ligne.
        arg_min({'montant': montant_rationalise, 'anomalie': montant_anomalie}, file_row_number)
            FILTER (WHERE montant_rationalise IS NOT NULL) AS source_montant,
        count(*) AS nb_titulaires,
        bool_and(titulaire_personne_morale) AS titulaires_personnes_morales
    FROM decp_lignes
    GROUP BY uid
)
SELECT
    * EXCLUDE (source_montant),
    source_montant.montant AS montant,
    nullif(trim(source_montant.anomalie), '') AS montant_anomalie,
    -- Fiable : strictement positif et sans anomalie signalée (une anomalie vide = aucune).
    coalesce(source_montant.montant > 0 AND nullif(trim(source_montant.anomalie), '') IS NULL, false) AS montant_fiable
FROM m;


-- 3. Les titulaires : une ligne par couple marché-titulaire, prête à publier.
--    L'identité et la localisation d'un titulaire qui n'est pas une personne
--    morale avérée sont retirées ; il compte toujours dans les totaux.

CREATE OR REPLACE VIEW decp_titulaires AS
SELECT
    l.uid,
    l.titulaire_personne_morale,
    CASE WHEN l.titulaire_personne_morale THEN l.titulaire_id END AS titulaire_id,
    CASE WHEN l.titulaire_personne_morale THEN l.titulaire_typeIdentifiant END AS titulaire_typeIdentifiant,
    CASE WHEN l.titulaire_personne_morale THEN l.titulaire_siren END AS titulaire_siren,
    CASE WHEN l.titulaire_personne_morale THEN l.titulaire_nom END AS titulaire_nom,
    CASE WHEN l.titulaire_personne_morale THEN l.titulaire_departement END AS titulaire_departement,
    l.titulaire_categorie,
    m.acheteur_id,
    m.acheteur_nom,
    m.acheteur_departement,
    m.cpv_division,
    m.dateNotification,
    m.nb_titulaires,
    m.montant_fiable,
    -- Groupement : le montant du marché partagé à parts égales (une convention, pas une donnée).
    CASE WHEN m.montant_fiable THEN m.montant / m.nb_titulaires END AS montant_part
FROM decp_lignes AS l
JOIN decp_marches AS m USING (uid);


-- 4. Le journal : ce qui a été lu, écarté et retenu.

CREATE OR REPLACE VIEW decp_journal AS
WITH b AS (
    SELECT
        count(*) AS lignes_lues,
        count(*) FILTER (WHERE TRY_CAST(donneesActuelles AS BOOLEAN) IS NOT TRUE) AS versions_non_actuelles,
        count(*) FILTER (WHERE TRY_CAST(donneesActuelles AS BOOLEAN) IS TRUE
                           AND TRY_CAST(dateNotification AS DATE) IS NULL) AS sans_date,
        count(*) FILTER (WHERE TRY_CAST(donneesActuelles AS BOOLEAN) IS TRUE
                           AND TRY_CAST(dateNotification AS DATE) < decp_depuis()) AS avant_periode,
        count(*) FILTER (WHERE TRY_CAST(donneesActuelles AS BOOLEAN) IS TRUE
                           AND TRY_CAST(dateNotification AS DATE) >= decp_depuis()
                           AND nullif(trim(uid), '') IS NULL) AS sans_uid,
        count(*) FILTER (WHERE TRY_CAST(donneesActuelles AS BOOLEAN) IS TRUE
                           AND TRY_CAST(dateNotification AS DATE) >= decp_depuis()
                           AND nullif(trim(uid), '') IS NOT NULL) AS identifiees
    FROM decp_brut
),
l AS (SELECT count(*) AS lignes_retenues FROM decp_lignes),
m AS (
    SELECT
        count(*) AS marches,
        count(*) FILTER (WHERE montant_fiable) AS marches_montant_fiable,
        min(dateNotification) AS premiere_notification,
        max(dateNotification) AS derniere_notification
    FROM decp_marches
)
SELECT
    decp_depuis() AS depuis,
    b.lignes_lues,
    b.versions_non_actuelles,
    b.sans_date,
    b.avant_periode,
    b.sans_uid,
    b.identifiees - l.lignes_retenues AS titulaires_repetes,
    l.lignes_retenues,
    m.marches,
    m.marches_montant_fiable,
    m.premiere_notification,
    m.derniere_notification
FROM b, l, m;
