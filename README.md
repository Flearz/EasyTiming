# Chronométreur de Course Python

## Description

Cette application Python avec interface graphique (Tkinter) permet de chronométrer des courses. Elle gère l'importation de listes de participants, le chronométrage par catégorie, l'enregistrement des arrivées et des abandons, et l'exportation des résultats dans des fichiers CSV. L'application inclut également une fonctionnalité de récupération de session en cas de fermeture inattendue.

## Fonctionnalités

* **Importation de Participants** : Importe les listes de départ depuis des fichiers CSV (délimiteur virgule ou point-virgule).
    * Recherche dynamique dans la liste des participants importés.
* **Gestion des Catégories** :
    * Sélection de la catégorie de course à chronométrer.
    * Affichage des distances spécifiques (Hommes/Femmes) pour la catégorie sélectionnée, lues depuis un fichier `categories.ini`.
* **Chronométrage** :
    * Boutons Start / Fin Course / Réinitialisation.
    * Enregistrement des temps d'arrivée dans un buffer.
    * Assignation des dossards aux temps bufferisés.
    * Possibilité de marquer un participant comme "Abandon".
* **Gestion Manuelle des Résultats** :
    * Ajout manuel d'un temps ou d'un abandon pour un dossard spécifique.
    * Suppression d'un temps d'arrivée enregistré par erreur dans le buffer.
* **Exportation des Résultats** :
    * Exportation automatique des résultats au format CSV lorsque la course est terminée.
    * Exportation manuelle possible.
    * Les fichiers de résultats sont nommés avec la catégorie et un numéro d'instance si la même course est exportée plusieurs fois (`resultats_[Categorie]_course_X.csv`).
    * Le CSV inclut :
        * Informations sur la catégorie et les distances.
        * Classement Scratch Général (pour la catégorie sélectionnée).
        * Classements par sexe (Hommes/Femmes) pour la catégorie sélectionnée.
        * Liste des abandons par sexe pour la catégorie sélectionnée.
* **Récupération de Session** :
    * Sauvegarde automatique de l'état de la course (chrono, buffer, classements en cours, catégorie, chemin du fichier participants) dans `race_recovery_state.json`.
    * Proposition de restauration de la session précédente au démarrage de l'application si un état sauvegardé est trouvé.
    * Tentative de rechargement automatique de la dernière liste de participants importée lors de la restauration.
* **Interface Utilisateur** :
    * Interface à onglets (Import, Chrono, Export).
    * Feedback visuel pour les opérations (ex: enregistrement de dossard) sans popups intempestifs.
    * Copyright affiché en bas de la fenêtre.
* **Configuration** :
    * Les distances par catégorie et par sexe sont configurables via un fichier `categories.ini`.

## Prérequis

* Python 3.x
* Tkinter (généralement inclus avec les installations standard de Python)
* Les bibliothèques Python standard : `csv`, `configparser`, `datetime`, `logging`, `json`, `os`, `pathlib`.

## Installation

1.  Assurez-vous que Python 3 est installé sur votre système.
2.  Téléchargez le fichier `race_timer_app.py` (ou le nom que vous lui avez donné).
3.  Placez le script `race_timer_app.py` dans un répertoire de votre choix.

## Configuration

### 1. Fichier des Participants (CSV)

* Créez un fichier CSV (extension `.csv` ou `.txt`) pour la liste de départ.
* L'application essaie de détecter automatiquement le délimiteur (virgule `,` ou point-virgule `;`).
* L'encodage du fichier devrait être UTF-8 (idéalement UTF-8 avec BOM pour une meilleure compatibilité avec Excel) ou un encodage commun comme CP1252 (Windows Latin-1).
* **Format des colonnes (l'ordre est important) :**
    1.  `N° Dossard` (ou `N. Dossard`, `Dossard`, `N`, `No Dossard`, `No. Dossard`) : Numéro de dossard (doit être un nombre).
    2.  `Nom` : Nom du participant.
    3.  `Prénom` (ou `Prenom`) : Prénom du participant.
    4.  `Sexe` (ou `Sex`) : Sexe du participant (ex: `h`, `f`, `H`, `F`). Sera converti en minuscules en interne.
    5.  `Catégorie` (ou `Categorie`, `Cat`) : Catégorie de course du participant.
* La première ligne peut contenir les en-têtes de colonnes.

    **Exemple de contenu de fichier `liste_participants.csv` :**
    ```csv
    N° Dossard;Nom;Prénom;Sexe;Catégorie
    1;Dupont;Hugo;h;Elite
    2;Martin;Emma;f;Elite
    10;Durand;Pierre;H;Populaire
    11;Petit;Alice;F;Populaire
    ```

### 2. Fichier des Distances (`categories.ini`)

* Créez un fichier nommé `categories.ini` **dans le même répertoire que le script `race_timer_app.py`**.
* Ce fichier définit les distances (en mètres) pour chaque catégorie, séparément pour les hommes et les femmes.
* **Format du fichier :**
    ```ini
    [Distances_H]
    Elite = 7700
    Populaire = 3500
    A = 300

    [Distances_F]
    Elite = 5200
    Populaire = 2400
    A = 300
    ```
* **Important :** Les noms de catégories dans ce fichier (ex: `Elite`, `Populaire`, `A`) doivent correspondre **exactement** (après suppression des espaces de début/fin et mise de la première lettre en majuscule, le reste en minuscules, ex: "Elite" deviendra "Elite", "elite" deviendra "Elite", " course a " deviendra "Course a") à ceux utilisés dans votre fichier de participants pour que les distances soient correctement associées.

## Utilisation

1.  Exécutez le script Python :
    ```bash
    python race_timer_app.py
    ```
    (Ou lancez-le via votre IDE Python préféré).

2.  **Onglet "Import"** :
    * Cliquez sur "Importer liste de départ" et sélectionnez votre fichier CSV de participants.
    * La liste des participants s'affichera. Vous pouvez utiliser le champ "Rechercher participant..." pour filtrer l'affichage par dossard, nom, prénom ou catégorie.
    * Cliquez sur "Suivant -> Chrono" pour passer à l'onglet de chronométrage.

3.  **Onglet "Chrono"** :
    * **Sélectionner une catégorie** : Choisissez la catégorie de course que vous souhaitez chronométrer dans la liste déroulante. Les distances correspondantes (Hommes/Femmes) s'afficheront en dessous.
    * **Démarrer la course** : Cliquez sur "Start" au moment du départ. Le chronomètre se lancera.
    * **Nouvelle arrivée** : Lorsqu'un coureur franchit la ligne, cliquez sur "Nouvelle arrivée". Le temps est enregistré dans le buffer "Arrivées en attente".
    * **Assigner un dossard** :
        * Entrez le numéro de dossard du coureur arrivé dans le champ "Dossard".
        * Cliquez sur "Valider Dossard". Le premier temps en attente dans le buffer sera assigné à ce dossard.
        * Un message de confirmation (ou d'erreur) s'affichera brièvement à côté des boutons.
    * **Marquer un abandon** :
        * Entrez le numéro de dossard du coureur.
        * Cliquez sur "Marquer Abandon". Le participant sera enregistré comme ayant abandonné (pas de temps consommé du buffer).
    * **Supprimer une arrivée du buffer** : Si vous avez cliqué sur "Nouvelle arrivée" par erreur, sélectionnez le temps erroné dans la liste "Arrivées en attente" et cliquez sur "Supprimer Arrivée Sélectionnée".
    * **Ajout Manuel de Résultat** :
        * Entrez le "Dossard", le "Temps (HH:MM:SS)" et cochez "Abandon" si nécessaire.
        * Cliquez sur "Ajouter Manuel". Utile pour corriger une erreur ou ajouter un résultat manquant.
    * **Fin de la course** : Cliquez sur "Fin Course" lorsque la course pour la catégorie est terminée. Cela arrêtera le chronomètre et déclenchera automatiquement une tentative d'exportation des résultats.
    * **Réinitialiser** : Cliquez sur "Réinit." pour remettre à zéro le chronomètre, le buffer et les classements pour la catégorie actuelle. Une confirmation vous sera demandée si des données existent.

4.  **Onglet "Export"** :
    * Cliquez sur "Exporter résultats" pour sauvegarder manuellement les classements de la catégorie actuellement sélectionnée dans un fichier CSV.
    * L'exportation est également tentée automatiquement à la fin d'une course (via le bouton "Fin Course").
    * Si l'écriture du fichier échoue (ex: fichier ouvert ailleurs), une option pour réessayer vous sera proposée.

## Fonctionnalité de Récupération

* Si l'application se ferme de manière inattendue (crash, coupure de courant) alors qu'une course était en cours ou que des données étaient présentes, elle tentera de sauvegarder l'état actuel.
* Au prochain démarrage, un message vous proposera de restaurer cette session.
* Si vous acceptez, l'application tentera de recharger :
    * La dernière liste de participants importée (si le chemin du fichier a été sauvegardé).
    * La catégorie qui était sélectionnée.
    * Le buffer d'arrivées.
    * Les classements déjà enregistrés.
    * L'état du chronomètre (en cours ou arrêté) et son heure de démarrage.
* **Note importante sur la restauration du chrono** : Si le chronomètre était en cours, il reprendra son décompte à partir de l'heure de démarrage sauvegardée. Vous devrez **manuellement tenir compte du temps écoulé pendant que l'application était fermée** si cela est pertinent pour votre chronométrage. L'objectif principal est la préservation des données.
* L'application passera automatiquement à l'onglet "Chrono" après une restauration réussie.

## Format d'Exportation CSV

Le fichier CSV exporté contient :
* Le nom de la catégorie et les distances Hommes/Femmes.
* Le "Classement Scratch Général (valides)" pour la catégorie.
* Pour chaque sexe (Hommes, Femmes) :
    * Le classement spécifique à ce sexe pour la catégorie.
    * La liste des abandons pour ce sexe.

Les sections sont toujours présentes, même si elles sont vides (ex: aucun abandon pour un sexe).

## Copyright

© Rihen \[Année Actuelle]
