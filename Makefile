.PHONY: setup migrations migrate run superuser shell dbshell \
	tests coverage lint \
	up up-prod down test-docker clean

setup:
	python -m venv .venv
	poetry install --no-root
	pre-commit install

migrations:
	python manage.py makemigrations

migrate:
	python manage.py migrate

run:
	python manage.py runserver

superuser:
	python manage.py createsuperuser

shell:
	python manage.py shell

dbshell:
	python manage.py dbshell

tests:
	python manage.py test

coverage:
	coverage run manage.py test
	coverage report

lint:
	pre-commit run --all-files

up:
	docker-compose up --build

up-prod:
	docker-compose -f docker-compose.prod.yml up --build

down:
	docker-compose down

test-docker:
	docker-compose run --rm web sh -c "coverage run manage.py test && coverage report"

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	rm -f .coverage
