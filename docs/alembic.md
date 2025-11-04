# Alembic Usage Guide

This repository uses **Alembic** to version-control the authentication service schema. Follow the steps below whenever you need to apply existing migrations or create new ones.

## 1. Prerequisites

- Python 3.11+ available locally.
- The `auth-db` Postgres container running (easiest via `docker compose up -d auth-db` from the repo root).
- PowerShell examples assume Windows; adapt activation commands if you use another shell.

## 2. Set up a virtual environment

```pwsh
cd csc3104_elderly_platform/authentication-svc
python -m venv .venv
. .venv/Scripts/Activate.ps1    # use .venv/bin/activate on bash/zsh
```

Install dependencies, including Alembic:

```pwsh
pip install -r requirements.txt alembic==1.13.1
```

## 3. Configure the database URL

When running migrations from the host machine, the auth database is exposed on port `55321` (see `docker-compose.yml`). Update Alembic’s connection string in one of two ways:

1. **Edit `alembic.ini`** – set  
   `sqlalchemy.url = postgresql+psycopg://auth:authpwd@localhost:55321/authentication`

2. **Or pass it at runtime** – keep `alembic.ini` unchanged and run commands with:  
   `alembic -x db_url=postgresql+psycopg://auth:authpwd@localhost:55321/authentication <command>`

> When you run migrations inside the Docker service (`docker compose run --rm authentication-svc …`), keep using `auth-db:5432` because the container can reach the database on the internal Docker network.

## 4. Apply migrations

```pwsh
alembic upgrade head
```

Run this after pulling changes to ensure your schema matches the current migrations.

## 5. Create a new migration

1. Make your SQLAlchemy model changes (e.g., in `app/models.py`).
2. Generate a migration:

   ```pwsh
   alembic revision --autogenerate -m "describe your change"
   ```

3. Review the generated script under `alembic/versions/` and adjust it if necessary.
4. Apply it locally with `alembic upgrade head`, then commit both the model changes _and_ the new revision file.

## 6. Running Alembic inside Docker

If you prefer to run migrations in the container environment:

```pwsh
docker compose run --rm authentication-svc alembic upgrade head
```

This uses the same configuration but connects to the database through the internal host `auth-db:5432`.

## 7. Team reminders

- Always commit migration files along with related model updates.
- After pulling from Git, developers should run `alembic upgrade head` before starting the services.
- Keep the instructions in this document updated if ports or dependencies change.

