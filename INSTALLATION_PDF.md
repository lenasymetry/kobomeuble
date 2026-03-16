# Installation de weasyprint pour l'export PDF

Pour générer des fichiers PDF des feuilles d'usinage, vous devez installer `weasyprint`.

## Installation de base

```bash
pip install weasyprint
```

## Dépendances système (selon votre OS)

### macOS

```bash
# Installer les dépendances système via Homebrew
brew install cairo pango gdk-pixbuf libffi

# Puis installer weasyprint
pip install weasyprint
```

### Linux (Ubuntu/Debian)

```bash
# Installer les dépendances système
sudo apt-get update
sudo apt-get install python3-cffi python3-brotli libpango-1.0-0 libpangoft2-1.0-0

# Puis installer weasyprint
pip install weasyprint
```

### Windows

Généralement, l'installation via pip suffit :

```bash
pip install weasyprint
```

Si vous rencontrez des erreurs, vous pouvez essayer d'installer GTK+ pour Windows depuis : https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer

## Vérification de l'installation

Pour vérifier que weasyprint est bien installé, vous pouvez exécuter dans un terminal Python :

```python
from weasyprint import HTML
print("weasyprint est installé correctement !")
```

## Utilisation

Une fois weasyprint installé, le bouton "📑 Télécharger Dossier Plans (PDF)" apparaîtra automatiquement dans la section Exportation de l'application.

Le PDF généré contiendra toutes les feuilles d'usinage du projet au format A4 paysage, avec des sauts de page automatiques entre chaque feuille.
