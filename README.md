# Analytics Service

Microservice **Python** calculant les **indicateurs (KPI) du réseau Good Food** :
chiffre d'affaires, volume de commandes, panier moyen, top plats, top restaurants.

Il ne possède **aucune donnée métier** : il agrège à la demande ce que les autres
services exposent, en réutilisant le JWT de l'appelant. Sa base ne sert qu'à
mettre en cache le résultat.

| | |
|---|---|
| **Langage / techno** | Python 3.13, FastAPI, uvicorn, asyncpg, httpx, PyJWT |
| **Base de données** | PostgreSQL (port hôte `5439`) — cache uniquement |
| **Port HTTP** | `8091` |
| **Documentation API** | http://localhost:8091/docs |

---

## Architecture — Clean / Hexagonale

La même découpe que les services Go, transposée en Python :

```
app/main.py                # Démarrage, migrations, injection des dépendances
app/config.py              # Configuration typée depuis l'environnement
app/
├── domain/                # Agrégation pure (aucun HTTP, aucune base), erreurs typées, ports
├── application/           # Cas d'usage : vue réseau (siège), vue restaurant (franchisé)
└── adapter/
    ├── http/              # Routeur FastAPI, middleware JWT + logs JSON, DTO
    ├── clients/           # Clients HTTP vers order-service et franchise-service
    └── postgres/          # Cache des snapshots + migrations SQL
tests/                     # 23 tests — domaine, cas d'usage, JWT
```

Le calcul des KPI vit entièrement dans `domain/metrics.py` sous forme de
fonctions pures : il se teste sans base ni serveur HTTP.

---

## Fonctionnalités

### Vue réseau — siège (`admin`)
- **CA total**, nombre de commandes, panier moyen, commandes annulées
- **Évolution jour par jour** (un point par jour, y compris les jours à zéro,
  pour que les courbes restent continues)
- **Top 5 des plats** par quantité vendue
- **Top 5 des restaurants** par chiffre d'affaires
- **Répartition par statut** de commande

### Vue restaurant — franchisé (`manager`)
Les mêmes indicateurs, restreints à **son propre restaurant**. Le siège peut
consulter n'importe quel restaurant via `?restaurantId=`.

### Règles de calcul
- Une commande **annulée** est comptée (le taux d'annulation reste visible) mais
  ne génère **jamais** de chiffre d'affaires
- Le panier moyen se calcule sur les seules commandes facturables
- La fenêtre par défaut est de **30 jours** (`?days=`, 1 à 365)

---

## Endpoints

| Méthode | Route | Accès | Description |
|---|---|---|---|
| `GET` | `/healthz` | public | Liveness |
| `GET` | `/readyz` | public | Readiness (base joignable) |
| `GET` | `/docs` | public | Documentation interactive (Swagger UI) |
| `GET` | `/api/analytics/network?days=30` | `admin` | KPI de tout le réseau |
| `GET` | `/api/analytics/restaurant?days=30` | `manager` | KPI de son restaurant |
| `GET` | `/api/analytics/restaurant?restaurantId=…` | `admin` | KPI d'un restaurant précis |

---

## Isolation multi-tenant

Un franchisé ne peut **jamais** lire les chiffres d'un autre restaurant. La règle
est appliquée **deux fois** :

1. **Ici** — le restaurant est déduit du `tenant_id` du JWT ; un `restaurantId`
   qui ne correspond pas renvoie `403`
2. **En amont** — chaque appel à `order-service` transporte le JWT **de
   l'appelant** (jamais un compte de service), donc order-service applique ses
   propres contrôles

---

## Dépendances aux autres services

| Service | Criticité | Sans lui |
|---|---|---|
| **auth-service** | 🔴 Critique | Aucun JWT à valider : tous les endpoints renvoient `401` |
| **order-service** | 🔴 Critique | C'est la source des commandes : plus aucun KPI calculable |
| **franchise-service** | 🟠 Importante | Les KPI restent calculés, mais les restaurants s'affichent sous un nom générique |

Ce service n'est requis par **aucun autre** : s'il est arrêté, seuls les
tableaux de bord perdent leurs chiffres, le reste de la plateforme fonctionne.

---

## Lancement

```bash
cp .env.example .env     # puis renseigner JWT_SECRET (le même que les autres services)
docker network create microservices-net   # si ce n'est pas déjà fait
docker compose up -d --build
```

## Développement local

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest      # 23 tests
.venv/bin/python -m ruff check .
```
