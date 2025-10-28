COMPOSE_FILE := $(CURDIR)/docker-compose.yml

.PHONY: up down logs

up:
	docker compose -f $(COMPOSE_FILE) up --build -d

down:
	docker compose -f $(COMPOSE_FILE) down

logs:
	docker compose -f $(COMPOSE_FILE) logs -f
