# Geneam

Application web de généalogie personnelle, conteneurisée avec Docker.

## Stack

- **Django 5** (Python) + **PostgreSQL** pour l'application
- **Nginx Proxy Manager** (conteneur `npm`) comme reverse proxy / gestion TLS
- **Docker Compose** pour orchestrer les 3 services (`web`, `db`, `npm`)

## Modèle de données (squelette)

- `Person` : identité civile (nom, prénom, sexe, naissance, décès, notes)
- `Parentage` : lien parent → enfant (biologique / adoptif / famille d'accueil)
- `Union` : lien entre deux personnes (mariage, PACS, union libre...)

Gestion CRUD complète disponible immédiatement via l'admin Django (`/admin/`,
protégé par l'authentification intégrée de Django). Une vue publique minimale
liste les personnes et affiche une fiche par personne (parents / enfants /
conjoint·e·s) — accessible sans connexion, l'application étant réservée à un
usage strictement personnel sur le réseau local.

## Démarrage

```bash
cp .env.example .env
# éditez .env : DJANGO_SECRET_KEY, mots de passe, hosts autorisés...

docker compose up -d --build
docker compose ps        # les 3 services doivent être "healthy"/"running"
docker compose logs -f web   # vérifier migrate + création du superuser
```

L'app est alors joignable en local sur `http://127.0.0.1:8000/` (uniquement
depuis le Pi lui-même) et prête à être proxyée par Nginx Proxy Manager, dont
l'interface d'administration est sur `http://<ip-du-pi>:81/` (identifiants
par défaut affichés au premier lancement — à changer immédiatement).

## Configuration de Nginx Proxy Manager

**Non automatisée ici** — à faire soi-même dans l'interface NPM (`:81`) :

1. Créer un **Proxy Host** avec comme nom de domaine `geneam.home.3airdutemps.fr`,
   forward vers l'hôte `web`, port `8000` (les deux conteneurs partagent le
   même réseau Docker, NPM peut donc joindre `web` par son nom de service).
2. Onglet SSL : demander un certificat (Let's Encrypt via challenge DNS OVH,
   ou certificat de son choix), puis activer "Force SSL".
3. Côté DNS : faire pointer `geneam.home.3airdutemps.fr` vers l'IP locale du
   Raspberry Pi (actuellement `192.168.1.212`) dans la zone OVH.

Si l'IP du Pi ou le nom de domaine changent, pensez à mettre à jour
`DJANGO_ALLOWED_HOSTS` et `DJANGO_CSRF_TRUSTED_ORIGINS` dans `.env`, puis
`docker compose up -d --build web`.

## Sauvegarde de la base

Les données PostgreSQL vivent dans le volume Docker nommé `pg_data`. Exemple
de sauvegarde :

```bash
docker compose exec db pg_dump -U geneam geneam > backup.sql
```
