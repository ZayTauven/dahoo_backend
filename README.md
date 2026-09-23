# Dahoo — API backend

API REST de gestion immobilière (biens, lots, baux, paiements, maintenance, annonces, abonnements).
Stack : Django 6.0, Django REST Framework, JWT (simplejwt), PostgreSQL.

## Installation locale

Prérequis : Python 3.13, PostgreSQL.

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows (source .venv/bin/activate sous Linux/macOS)
pip install -r requirements.txt

cp .env.example .env            # puis renseigner SECRET_KEY et les accès PostgreSQL
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

L'authentification se fait par numéro de téléphone :
`POST /api/v1/users/login/` avec `{"phone": "...", "password": "..."}` renvoie les jetons `access` et `refresh`.

## Configuration

Toute la configuration passe par les variables d'environnement décrites dans [.env.example](.env.example).
`SECRET_KEY` est obligatoire ; `DEBUG` vaut `False` par défaut, ce qui active les réglages HTTPS
(redirection SSL, cookies sécurisés, HSTS).

Avant un déploiement : `python manage.py check --deploy`.
