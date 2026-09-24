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

Puis faire de ce compte l'administrateur Dahoo (plateforme + organisation interne « Dahoo ») :

```bash
python manage.py setup_dahoo <téléphone>
```

## Plateforme Dahoo et agences

Dahoo est l'éditeur du SaaS : ses administrateurs (`is_staff`) gèrent les agences depuis
`/api/v1/platform/` (création d'une agence avec son premier administrateur, prolongation d'essai,
suspension, abonnements). Dahoo est aussi une agence : l'organisation interne (`is_internal`),
jamais soumise à l'essai ni à l'abonnement.

Les rôles sont communs à toutes les agences et gérés par l'admin Dahoo dans l'admin Django.
Les rôles système sont réalignés sur `access/catalog.py` à chaque `migrate` : pour un besoin
spécifique, créer un nouveau rôle plutôt que modifier un rôle système.

## Utiliser l'API

- Documentation interactive : `/api/docs/` (schéma OpenAPI : `/api/schema/`).
- Connexion par téléphone : `POST /api/v1/users/login/` avec `{"phone": "...", "password": "..."}`,
  puis en-tête `Authorization: Bearer <access>`.
- Toutes les données sont cloisonnées par **organisation** (agence). Un utilisateur membre de plusieurs
  organisations précise laquelle avec l'en-tête `X-Organization-ID`.
- Les droits passent par des **capabilities** (`property.view`, `lease.activate`...) portées par le rôle
  du membre. Le catalogue et les rôles système (`ORG_ADMIN`, `MANAGER`, `ACCOUNTANT`, `VIEWER`) sont
  définis dans [access/catalog.py](access/catalog.py) et synchronisés automatiquement à chaque `migrate`.
- **Locataires** : `/api/v1/leases/tenants/`. Chaque agence tient sa propre fiche (nom, email, pièce
  d'identité, notes) ; l'`id` renvoyé est celui attendu par `tenant` (bail) et `payer` (paiement).
- **Essai gratuit** : une nouvelle organisation dispose de `TRIAL_DAYS` jours (30 par défaut). Ensuite, sans
  abonnement actif, l'accès passe en lecture seule (écritures refusées en `402`). Le statut est exposé dans
  `access_status` (`TRIAL`, `ACTIVE`, `EXPIRED`) sur `/users/me/` et `/organizations/current/`. Le staff peut
  prolonger un essai (`trial_ends_at`) ou attribuer un abonnement depuis l'admin.

## Espace agence : listes

Les listes acceptent des filtres (`?status=`, `?unit=`...), `?search=` et `?ordering=` (préfixe `-`
pour l'ordre décroissant) sur les champs déclarés par chaque vue, visibles dans `/api/docs/`. Exemples :
`/leases/?status=ACTIVE&tenant=12`, `/payments/schedules/?is_paid=false&due_date_before=2026-10-31`,
`/payments/payments/?payment_date_after=2026-09-01`, `/properties/properties/?city=dakar&search=teranga`.
Les réponses portent des libellés en lecture seule (`unit_label`, `tenant_name`, `payer_name`,
`contract_label`...) pour éviter au front une requête par ligne. `GET /api/v1/properties/units/` liste
tous les lots de l'organisation (filtres `status`, `category`, `building`, `property`) pour les sélecteurs.

## Photos des annonces (médias)

- `GET|POST /api/v1/listings/<id>/photos/` : liste et envoi (multipart, champ `image`, plus `alt` et
  `position` facultatifs). JPEG, PNG ou WebP, 8 Mo et 20 photos maximum par annonce.
- `PATCH|DELETE /api/v1/listings/photos/<id>/` : texte alternatif, position, suppression (fichier compris).
- Droits : `listing.view` en lecture, `listing.update` en écriture. Les URL renvoyées sont absolues.

Les fichiers sont stockés dans `media/` (`MEDIA_ROOT`, non versionné). Django ne les sert qu'avec
`DEBUG=True` ; en production, les servir par le serveur web (ex. `location /media/` sous Nginx) ou
un stockage objet.

## API publique (portail d'annonces et vitrine)

`/api/v1/public/` : sans authentification (un en-tête `Authorization` est ignoré), limitée par IP
(`THROTTLE_ANON`). Seules les annonces **publiées** d'agences **actives** dont l'accès n'a pas expiré
(essai ou abonnement en cours, organisation interne) sont visibles ; aucune donnée privée n'est exposée
(locataires, bailleurs, prospects, baux, adresse exacte) et la position est arrondie à 3 décimales.

| Méthode | URL | Rôle |
|---|---|---|
| GET | `listings/` | Annonces paginées (`page`, `page_size` ≤ 50). Filtres : `listing_type`, `city`, `category`, `min_price`, `max_price`, `min_bedrooms`, `agency`, `q`. Tri `ordering` : `price`, `-price`, `-published_at` (défaut). |
| GET | `listings/<id>/` | Fiche : photos, description, contact de l'agence, `similar` (3 annonces du même type et de la même ville). |
| POST | `listings/<id>/interest/` | Demande de visite (`{"prospect": {"full_name", "phone", "email", "source"}, "message"}`), `THROTTLE_PUBLIC_INTEREST`. |
| GET | `agencies/`, `agencies/<id>/` | Agences ayant au moins une annonce publique (404 sinon). |
| GET | `stats/` | Compteurs par type, par catégorie, nombre d'agences, villes. |
| GET | `plans/` | Offres d'abonnement actives. |
| POST | `demo-requests/` | Formulaire « demander une démo » (`THROTTLE_DEMO_REQUEST`, 5/heure par défaut). |

Les demandes de démo se traitent dans l'admin Django ou via `GET /api/v1/platform/demo-requests/`
et `PATCH /api/v1/platform/demo-requests/<id>/` (`{"handled": true}`), réservés à l'équipe Dahoo.

Si le front appelle l'API publique depuis son serveur (rendu Next.js côté serveur), toutes les requêtes
arrivent de la même IP : augmenter `THROTTLE_ANON` ou faire transmettre l'IP du visiteur par un proxy.

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
