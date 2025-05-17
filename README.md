# Chronométreur de Course Python

## Description

Cette application Python avec interface graphique (Tkinter) permet de chronométrer des courses. Elle gère l'ajout et l'importation de listes de participants, la gestion des catégories (distances et années), le chronométrage par catégorie, l'enregistrement des arrivées et des abandons, et l'exportation des résultats dans des fichiers CSV. L'application inclut également une fonctionnalité de récupération de session en cas de fermeture inattendue. Les résultats sont sauvegardés dans un sous-dossier "résultats".

## Fonctionnalités

* **Gestion des Inscriptions (Onglet "Inscriptions")** :
    * Ajout manuel de participants directement dans le fichier `liste_departs.csv`.
        * Champs : N° Dossard, Nom, Prénom, Sexe (h/f), Catégorie (sélection depuis `categories.ini`).
        * **Vérification de dossard existant** : Empêche l'ajout si le dossard est déjà présent dans `liste_departs.csv`.
        * **Rechargement automatique** : La liste des participants dans l'application est mise à jour automatiquement après chaque ajout réussi.
    * **Gestion des Catégories** :
        * Bouton "Gérer" ouvrant un popup dédié.
        * Visualisation des catégories existantes (Nom, Années, Dist. H, Dist. F) dans un tableau.
        * Ajout/Modification de catégories : Nom, Années, Distance Hommes (m), Distance Femmes (m).
        * Les modifications sont sauvegardées dans `categories.ini` et l'interface est mise à jour.

* **Liste des Participants (Onglet "Liste Participants")** :
    * Affiche la liste des participants actuellement chargés.
    * **Recherche dynamique** par Dossard, Nom, Prénom, ou Catégorie.
    * **Bouton "Recharger Liste de Départ"** : Recharge directement le fichier `liste_departs.csv` (situé à côté de l'application). Une confirmation est demandée si une course est en cours.
    * **Bouton "Supprimer Participant(s) Sélectionné(s)"** : Permet de supprimer des participants de la liste en mémoire et du fichier `liste_departs.csv` (après confirmation).
    * Barre de défilement pour les longues listes.

* **Chronométrage (Onglet "Chrono")** :
    * Sélection de la catégorie de course à chronométrer.
    * Affichage des distances (Hommes/Femmes) pour la catégorie sélectionnée.
    * **Bouton "Afficher Liste de Course (Cat. Actuelle)"** : Ouvre une fenêtre popup avec la liste des participants de la catégorie en cours, triée par nom, avec un champ de recherche. Barre de défilement incluse.
    * Boutons Start / Fin Course / Réinitialisation.
    * Enregistrement des temps d'arrivée dans un buffer.
    * Assignation des dossards aux temps bufferisés.
    * Possibilité de marquer un participant comme "Abandon".
    * Barre de défilement pour le buffer d'arrivées.

* **Gestion Manuelle des Résultats (dans l'onglet "Chrono")** :
    * Ajout manuel d'un temps ou d'un abandon pour un dossard spécifique.
    * Suppression d'un temps d'arrivée enregistré par erreur dans le buffer.

* **Exportation des Résultats (Onglet "Export" et Automatique)** :
    * Exportation automatique des résultats au format CSV lorsque la course est terminée (via "Fin Course").
    * Exportation manuelle possible depuis l'onglet "Export".
    * Les fichiers de résultats sont sauvegardés dans un sous-dossier nommé "**résultats**" (créé s'il n'existe pas) à côté de l'application.
    * Nom des fichiers : `resultats_[Categorie]_course_X.csv` (numérotés si exportations multiples).
    * Le CSV inclut :
        * Informations sur la catégorie, les distances (H/F) et les **Années**.
        * Classement Scratch Général.
        * Classements par sexe (Hommes/Femmes).
        * Liste des abandons par sexe.

* **Récupération de Session** :
    * Sauvegarde automatique de l'état de la course dans `race_recovery_state.json`.
    * Proposition de restauration de la session précédente au démarrage.
    * Tentative de rechargement de la dernière liste de participants utilisée.

* **Interface Utilisateur** :
    * Interface à onglets claire et organisée.
    * Feedback visuel pour les opérations.
    * Copyright.

## Prérequis

* Python 3.x
* Tkinter (généralement inclus avec les installations standard de Python)

## Installation

1.  Assurez-vous que Python 3 est installé sur votre système.
2.  Téléchargez le script `race_timer_app.py`.
3.  Placez le script `race_timer_app.py` dans un répertoire de votre choix.
4.  Créez (ou laissez l'application créer/gérer) les fichiers suivants dans le **même répertoire** que `race_timer_app.py` :
    * `categories.ini` (voir section Configuration ci-dessous)
    * `liste_departs.csv` (peut être créé/modifié via l'onglet "Inscriptions" ou manuellement)

## Configuration

### 1. Fichier des Catégories (`categories.ini`)

* Ce fichier définit les informations pour chaque catégorie.
* Il doit être nommé `categories.ini` et placé à côté de `race_timer_app.py` (ou de l'exécutable).
* **Format du fichier (une section par catégorie)** :
    ```ini
    [NomDeLaCategorie]
    distance_h = <distance en mètres pour les hommes>
    distance_f = <distance en mètres pour les femmes>
    annees = <information sur la tranche d'âge, ex: 2010-2011 ou U12>

    [Elite]
    distance_h = 7700
    distance_f = 5200
    annees = 2007 et plus âgé(e)s

    [A]
    distance_h = 300
    distance_f = 300
    annees = 2020 et plus jeunes
    ```
* **Important** : Les noms de catégories dans ce fichier (ex: `Elite`, `A`) sont normalisés par le script (`strip().capitalize()`). Assurez-vous que les noms de catégories dans votre fichier de participants, une fois normalisés de la même manière, correspondent pour que les informations soient correctement associées. Vous pouvez gérer ce fichier via le bouton "Gérer" dans l'onglet "Inscriptions".

### 2. Fichier des Participants (`liste_departs.csv`)

* Ce fichier contient la liste de départ. Il peut être créé/modifié via l'onglet "Inscriptions" ou préparé manuellement.
* L'application s'attend à un délimiteur **point-virgule (`;`)**.
* Encodage recommandé : UTF-8 (avec ou sans BOM) ou CP1252.
* **Format des colonnes (l'ordre est important, avec en-tête)** :
    1.  `N° Dossard`
    2.  `Nom`
    3.  `Prénom`
    4.  `Sexe` (valeurs attendues : `h` ou `f`, la casse est ignorée en interne)
    5.  `Catégorie`
    ```csv
    N° Dossard;Nom;Prénom;Sexe;Catégorie
    1;Dupont;Hugo;h;Elite
    2;Martin;Emma;f;A
    ```

## Utilisation

1.  Exécutez le script Python : `python race_timer_app.py` (ou lancez l'exécutable).
2.  **Onglet "Inscriptions"** :
    * Utilisez les champs pour ajouter de nouveaux participants au fichier `liste_departs.csv`. Le dossard doit être unique.
    * Cliquez sur "Gérer" pour ouvrir le popup de gestion des catégories (distances, années).
3.  **Onglet "Liste Participants"** :
    * La liste des participants de `liste_departs.csv` est chargée automatiquement au démarrage.
    * Utilisez "Rechercher participant..." pour filtrer l'affichage.
    * Cliquez sur "Recharger Liste de Départ" pour actualiser la liste depuis `liste_departs.csv`.
    * Sélectionnez un ou plusieurs participants et cliquez sur "Supprimer Participant(s) Sélectionné(s)" pour les retirer (après confirmation).
    * Cliquez sur "Suivant -> Chrono" pour passer à l'onglet de chronométrage.
4.  **Onglet "Chrono"** :
    * **Sélectionner une catégorie** : Choisissez la catégorie à chronométrer. Les distances H/F s'affichent.
    * Cliquez sur "Afficher Liste de Course (Cat. Actuelle)" pour voir les participants de cette catégorie.
    * **Démarrer la course** : Cliquez sur "Start".
    * **Nouvelle arrivée** : Cliquez sur "Nouvelle arrivée" (le temps est bufferisé).
    * **Assigner un dossard** : Entrez le N° Dossard, puis "Valider Dossard".
    * **Marquer un abandon** : Entrez le N° Dossard, puis "Marquer Abandon".
    * Utilisez les options de gestion manuelle ou de suppression du buffer si besoin.
    * **Fin de la course** : Cliquez sur "Fin Course" (arrête le chrono et exporte les résultats).
    * **Réinitialiser** : Cliquez sur "Réinit." pour la catégorie actuelle (avec confirmation).
5.  **Onglet "Export"** :
    * Cliquez sur "Exporter résultats" pour une sauvegarde manuelle des classements de la catégorie en cours. Les fichiers sont placés dans le dossier "résultats".

## Création d'un Exécutable (.exe) avec PyInstaller

Pour distribuer votre application comme un fichier exécutable unique sous Windows :

1.  **Installez PyInstaller** (si ce n'est pas déjà fait) :
    ```bash
    pip install pyinstaller
    ```
2.  **Placez-vous dans le répertoire de votre script** :
    Dans un terminal, naviguez (`cd`) jusqu'au dossier contenant `race_timer_app.py`.
3.  **Exécutez PyInstaller** :
    ```bash
    pyinstaller --onefile --windowed --name RaceTimer race_timer_app.py
    ```
    * `--onefile` : Crée un seul fichier exécutable.
    * `--windowed` : Empêche l'affichage d'une console en arrière-plan.
    * `--name RaceTimer` : Nomme l'exécutable `RaceTimer.exe`.
4.  **Distribution** :
    * Après la compilation, trouvez `RaceTimer.exe` dans le sous-dossier `dist`.
    * Créez un nouveau dossier pour votre application (ex: "MonChronoCourse").
    * Copiez `RaceTimer.exe` dans ce nouveau dossier.
    * **Manuellement, placez votre fichier `categories.ini` dans ce même dossier**, à côté de `RaceTimer.exe`.
    * L'application créera `liste_departs.csv` (si non présent), `race_recovery_state.json`, et le dossier `résultats` dans ce même répertoire lors de son utilisation.

## Fonctionnalité de Récupération

* En cas de fermeture inattendue, l'application tente de sauvegarder l'état actuel dans `race_recovery_state.json`.
* Au prochain démarrage, une restauration de cette session est proposée.
* **Note sur la restauration du chrono** : Si le chronomètre était en cours, il reprendra son décompte. Tenez compte manuellement du temps écoulé pendant la fermeture si nécessaire.

## Format d'Exportation CSV

Le fichier CSV exporté contient :
* Le nom de la catégorie, les distances H/F, et les informations "Années".
* Le classement Scratch Général.
* Pour chaque sexe (Hommes, Femmes) :
    * Le classement spécifique.
    * La liste des abandons.

## Copyright

© Rihen 2024
