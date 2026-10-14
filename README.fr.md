<div align="center">

[English](README.md) · [Deutsch](README.de.md) · [Русский](README.ru.md) · [Français](README.fr.md) · [Español](README.es.md) · [Italiano](README.it.md) · [Português (Brasil)](README.pt-BR.md) · [Polski](README.pl.md) · [Українська](README.uk.md) · [日本語](README.ja.md) · [简体中文](README.zh-CN.md)

</div>

# PicardWulf v1.0

**Recherche de versions multisource, classement automatique et écriture sécurisée des tags pour MusicBrainz Picard 3.0.**

> **Statut :** version candidate. Tests locaux réussis ; activation réelle sur BMAX-B6, appels API et sauvegarde des tags encore à valider.

## Fonctionnalités

- Recherche simultanée sur MusicBrainz, Deezer et Apple/iTunes, ainsi que Spotify, SoundCloud et Last.fm avec les accès API nécessaires.
- Dès **Ajouter un dossier**, comparaison des sorties de tous les fournisseurs : titre, artiste, album, durée, ISRC et identifiants valides.
- **La meilleure version gagne**, sans priorité automatique à MusicBrainz ; Deezer ou Spotify peuvent être retenus si leur score est supérieur.
- En cas d'ambiguïté ou de conflit entre éditions, aucune application automatique.
- Seuls de véritables identifiants MusicBrainz peuvent charger un album dans le panneau natif de Picard ; les identifiants externes restent distincts.
- Les métadonnées sélectionnées sont proposées dans Picard. **L'écriture automatique des fichiers est désactivée** par défaut ; après activation explicite, une copie audio complète vérifiée SHA-256 précède chaque écriture.
- Conservation du renommage NEOWULF et correction « compilation ≠ Various Artists ». *Curtain Call 2* reste attribué à Eminem.

## Installation

Fermez Picard **3.0**, extrayez le paquet et lancez **`Install-NEOWULF.cmd`** sous l'utilisateur du bureau (`megal` sur BMAX-B6). Le dossier cible est `%APPDATA%\MusicBrainz\Picard\plugins3\neowulf_picard_repair`. Activez ensuite le plugin dans **Options → Plugins**. Le `picard-cli.exe` défectueux n'est pas utilisé.

## Utilisation et sécurité

**File → Add Folder** déclenche la recherche. **Tools → PicardWulf** propose le classement, la sauvegarde automatique avec confirmation et la revue manuelle ; **Tools → NEOWULF** affiche les sources, résultats et outils de renommage. L'application automatique requiert un score non ambigu d'au moins **93,5 %**. Les recherches peuvent transmettre titre et artiste aux fournisseurs activés ; leurs quotas et conditions restent applicables. Les véritables enregistrements sur disque ne sont pas validés avant un test de bout en bout sur BMAX-B6.

## Développement

```bash
python -m unittest discover -s tests -v
```

[Documentation détaillée en anglais](README.md) · [Journal des modifications](CHANGELOG.md) · [État](LAST_TASKS.md) · [Licence](LICENSE)


## v1.0 S2 – état du code

Le consentement par fournisseur, les états de disponibilité, les budgets et délais persistants ainsi que la gestion sûre des jetons sont implémentés. Les réponses incomplètes ne déclenchent aucune application automatique. Les sondes anonymes MusicBrainz/Deezer/iTunes et 145 tests passent ; les fournisseurs authentifiés et le fonctionnement sur BMAX restent à vérifier. Aucun nouvel abonnement.

[S2 evidence / Nachweise](docs/planning/S2-EXECUTION-2026-10-14.md).
