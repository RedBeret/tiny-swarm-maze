SHELL := /bin/bash

PYTHON ?= python3

.PHONY: backend-install backend-run frontend-install frontend-run frontend-build test verify docker-up docker-down

backend-install:
	cd backend && $(PYTHON) -m venv .venv && .venv/bin/python -m pip install -r requirements.txt

backend-run:
	cd backend && .venv/bin/python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

frontend-install:
	cd frontend && npm install

frontend-run:
	cd frontend && npm run dev

frontend-build:
	cd frontend && npm run build

test:
	cd backend && .venv/bin/python -m pytest -q

verify: test frontend-build

docker-up:
	docker compose up --build

docker-down:
	docker compose down
