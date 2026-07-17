# django-test

## Setup

```bash
python -m venv .venv
source .venv/Scripts/activate
poetry install --no-root
pre-commit install
```

## Migrations

```bash
python manage.py migrate
```

## Rodar o servidor

```bash
python manage.py runserver
```

## Testar o health check

```bash
curl http://127.0.0.1:8000/status/
```

Resposta esperada:

```json
{"status": "ok"}
```

## Linters

Rodam automaticamente antes de cada commit (via `pre-commit install`), mas também dá pra rodar manualmente:

```bash
pre-commit run --all-files
```

## Testes

```bash
python manage.py test
```
