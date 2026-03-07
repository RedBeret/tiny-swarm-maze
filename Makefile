SHELL := /bin/bash

.PHONY: backend-install backend-run frontend-install frontend-run test docker-up docker-down

backend-install:
	cd backend && python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt

backend-run:
	cd backend && source .venv/bin/activate && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

frontend-install:
	cd frontend && npm install

frontend-run:
	cd frontend && npm run dev

test:
	cd backend && source .venv/bin/activate && pytest -q

docker-up:
	docker compose up --build

docker-down:
	docker compose down
