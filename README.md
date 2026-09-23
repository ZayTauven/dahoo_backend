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

Pour démarrer, créer une organisation et y rattacher le superuser dans l'admin Django
(`/admin/` → Organizations, rôle `ORG_ADMIN`).

## Utiliser l'API

- Documentation interactive : `/api/docs/` (schéma OpenAPI : `/api/schema/`).
- Connexion par téléphone : `POST /api/v1/users/login/` avec `{"phone": "...", "password": "..."}`,
  puis en-tête `Authorization: Bearer <access>`.
- Toutes les données sont cloisonnées par **organisation** (agence). Un utilisateur membre de plusieurs
  organisations précise laquelle avec l'en-tête `X-Organization-ID`.
- Les droits passent par des **capabilities** (`property.view`, `lease.activate`...) portées par le rôle
  du membre. Le catalogue et les rôles système (`ORG_ADMIN`, `MANAGER`, `ACCOUNTANT`, `VIEWER`) sont
  définis dans [access/catalog.py](access/catalog.py) et synchronisés automatiquement à chaque `migrate`.

## Tests

```bash
python manage.py test tests
```

Les tests tournent sur PostgreSQL (base de test temporaire créée puis détruite).

## Configuration

Toute la configuration passe par les variables d'environnement décrites dans [.env.example](.env.example).
`SECRET_KEY` est obligatoire ; `DEBUG` vaut `False` par défaut, ce qui active les réglages HTTPS
(redirection SSL, cookies sécurisés, HSTS).

Avant un déploiement : `python manage.py check --deploy`.
