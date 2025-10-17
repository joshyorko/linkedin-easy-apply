# ============================================================================
# LinkedIn Easy Apply Action Server - Makefile
# ============================================================================

# Variables
IMAGE_NAME ?= linkedin-easy-apply
IMAGE_TAG ?= latest
REGISTRY ?= 
FULL_IMAGE_NAME = $(if $(REGISTRY),$(REGISTRY)/$(IMAGE_NAME),$(IMAGE_NAME))

# Docker build arguments
DOCKER_BUILD_ARGS ?= --no-cache
PLATFORM ?= linux/amd64

# Colors for output
GREEN  := \033[0;32m
YELLOW := \033[0;33m
BLUE   := \033[0;34m
RED    := \033[0;31m
NC     := \033[0m # No Color

.PHONY: help
help: ## Show this help message
	@echo -e "$(BLUE)LinkedIn Easy Apply Action Server - Available Commands$(NC)"
	@echo -e ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[0;32m%-20s\033[0m %s\n", $$1, $$2}'

.PHONY: build
build: ## Build the Docker image
	@echo -e "$(BLUE)Building Docker image: $(FULL_IMAGE_NAME):$(IMAGE_TAG)$(NC)"
	docker build $(DOCKER_BUILD_ARGS) \
		--platform $(PLATFORM) \
		-t $(FULL_IMAGE_NAME):$(IMAGE_TAG) \
		-t $(FULL_IMAGE_NAME):latest \
		.
	@echo -e "$(GREEN)✓ Build complete: $(FULL_IMAGE_NAME):$(IMAGE_TAG)$(NC)"

.PHONY: build-fast
build-fast: ## Build without cache clearing (faster)
	@$(MAKE) build DOCKER_BUILD_ARGS=""

.PHONY: build-multiarch
build-multiarch: ## Build multi-architecture image (amd64, arm64)
	@echo -e "$(BLUE)Building multi-arch image: $(FULL_IMAGE_NAME):$(IMAGE_TAG)$(NC)"
	docker buildx build \
		--platform linux/amd64,linux/arm64 \
		-t $(FULL_IMAGE_NAME):$(IMAGE_TAG) \
		-t $(FULL_IMAGE_NAME):latest \
		--push \
		.
	@echo -e "$(GREEN)✓ Multi-arch build complete and pushed$(NC)"

.PHONY: login-registry
login-registry: ## Login to container registry (interactive)
	@echo -e "$(BLUE)Select container registry:$(NC)"
	@echo -e "  $(YELLOW)1)$(NC) Docker Hub (docker.io)"
	@echo -e "  $(YELLOW)2)$(NC) GitHub Container Registry (ghcr.io)"
	@echo -e "  $(YELLOW)3)$(NC) Google Container Registry (gcr.io)"
	@echo -e "  $(YELLOW)4)$(NC) Amazon ECR"
	@echo -e "  $(YELLOW)5)$(NC) Azure Container Registry (azurecr.io)"
	@echo -e "  $(YELLOW)6)$(NC) Custom registry"
	@echo -e ""
	@read -p "Enter choice [1-6]: " choice; \
	case $$choice in \
		1) \
			echo "$(BLUE)Logging into Docker Hub...$(NC)"; \
			read -p "Docker Hub username: " username; \
			docker login -u $$username docker.io; \
			;; \
		2) \
			echo "$(BLUE)Logging into GitHub Container Registry...$(NC)"; \
			read -p "GitHub username: " username; \
			echo "$(YELLOW)Use a Personal Access Token (PAT) with 'write:packages' scope$(NC)"; \
			docker login ghcr.io -u $$username; \
			;; \
		3) \
			echo "$(BLUE)Logging into Google Container Registry...$(NC)"; \
			echo "$(YELLOW)Make sure you have gcloud configured$(NC)"; \
			gcloud auth configure-docker gcr.io; \
			;; \
		4) \
			echo "$(BLUE)Logging into Amazon ECR...$(NC)"; \
			read -p "AWS Region (e.g., us-east-1): " region; \
			read -p "AWS Account ID: " account; \
			aws ecr get-login-password --region $$region | docker login --username AWS --password-stdin $$account.dkr.ecr.$$region.amazonaws.com; \
			;; \
		5) \
			echo "$(BLUE)Logging into Azure Container Registry...$(NC)"; \
			read -p "Registry name (e.g., myregistry): " registry; \
			az acr login --name $$registry; \
			;; \
		6) \
			echo "$(BLUE)Logging into custom registry...$(NC)"; \
			read -p "Registry URL: " registry; \
			read -p "Username: " username; \
			docker login $$registry -u $$username; \
			;; \
		*) \
			echo "$(RED)Invalid choice$(NC)"; \
			exit 1; \
			;; \
	esac

.PHONY: push
push: ## Push image to registry (set REGISTRY variable)
	@if [ -z "$(REGISTRY)" ]; then \
		echo "$(RED)Error: REGISTRY variable not set$(NC)"; \
		echo "$(YELLOW)Usage: make push REGISTRY=ghcr.io/username$(NC)"; \
		echo "$(YELLOW)   or: make push REGISTRY=docker.io/username$(NC)"; \
		exit 1; \
	fi
	@echo -e "$(BLUE)Pushing image: $(FULL_IMAGE_NAME):$(IMAGE_TAG)$(NC)"
	docker push $(FULL_IMAGE_NAME):$(IMAGE_TAG)
	docker push $(FULL_IMAGE_NAME):latest
	@echo -e "$(GREEN)✓ Push complete$(NC)"

.PHONY: push-ghcr
push-ghcr: ## Quick push to GitHub Container Registry (requires GITHUB_USER)
	@if [ -z "$(GITHUB_USER)" ]; then \
		echo "$(RED)Error: GITHUB_USER variable not set$(NC)"; \
		echo "$(YELLOW)Usage: make push-ghcr GITHUB_USER=yourusername$(NC)"; \
		exit 1; \
	fi
	@$(MAKE) push REGISTRY=ghcr.io/$(GITHUB_USER)

.PHONY: push-docker
push-docker: ## Quick push to Docker Hub (requires DOCKER_USER)
	@if [ -z "$(DOCKER_USER)" ]; then \
		echo "$(RED)Error: DOCKER_USER variable not set$(NC)"; \
		echo "$(YELLOW)Usage: make push-docker DOCKER_USER=yourusername$(NC)"; \
		exit 1; \
	fi
	@$(MAKE) push REGISTRY=$(DOCKER_USER)

.PHONY: run
run: ## Run the container locally
	@echo -e "$(BLUE)Starting container...$(NC)"
	docker run -d \
		--name linkedin-easy-apply \
		-p 8080:8080 \
		--env-file .env \
		$(FULL_IMAGE_NAME):$(IMAGE_TAG)
	@echo -e "$(GREEN)✓ Container started$(NC)"
	@echo -e "$(YELLOW)Access at: http://localhost:8080$(NC)"

.PHONY: run-it
run-it: ## Run container interactively with shell
	@echo -e "$(BLUE)Starting interactive container...$(NC)"
	docker run -it --rm \
		-p 8080:8080 \
		--env-file .env \
		$(FULL_IMAGE_NAME):$(IMAGE_TAG) \
		/bin/bash

.PHONY: stop
stop: ## Stop and remove the running container
	@echo -e "$(BLUE)Stopping container...$(NC)"
	docker stop linkedin-easy-apply || true
	docker rm linkedin-easy-apply || true
	@echo -e "$(GREEN)✓ Container stopped$(NC)"

.PHONY: logs
logs: ## Show container logs
	docker logs -f linkedin-easy-apply

.PHONY: shell
shell: ## Open a shell in the running container
	docker exec -it linkedin-easy-apply /bin/bash

.PHONY: compose-up
compose-up: ## Start with docker-compose
	@echo -e "$(BLUE)Starting services with docker-compose...$(NC)"
	docker-compose up -d
	@echo -e "$(GREEN)✓ Services started$(NC)"

.PHONY: compose-down
compose-down: ## Stop docker-compose services
	@echo -e "$(BLUE)Stopping services...$(NC)"
	docker-compose down
	@echo -e "$(GREEN)✓ Services stopped$(NC)"

.PHONY: compose-logs
compose-logs: ## Show docker-compose logs
	docker-compose logs -f

.PHONY: clean
clean: ## Clean up containers, images, and volumes
	@echo -e "$(BLUE)Cleaning up...$(NC)"
	docker-compose down -v || true
	docker stop linkedin-easy-apply || true
	docker rm linkedin-easy-apply || true
	@echo -e "$(GREEN)✓ Cleanup complete$(NC)"

.PHONY: clean-images
clean-images: ## Remove built images
	@echo -e "$(BLUE)Removing images...$(NC)"
	docker rmi $(FULL_IMAGE_NAME):$(IMAGE_TAG) || true
	docker rmi $(FULL_IMAGE_NAME):latest || true
	@echo -e "$(GREEN)✓ Images removed$(NC)"

.PHONY: prune
prune: ## Prune Docker system (removes unused data)
	@echo -e "$(YELLOW)Warning: This will remove all unused containers, networks, images$(NC)"
	@read -p "Continue? [y/N] " confirm; \
	if [ "$$confirm" = "y" ] || [ "$$confirm" = "Y" ]; then \
		docker system prune -af --volumes; \
		echo "$(GREEN)✓ System pruned$(NC)"; \
	else \
		echo "$(BLUE)Cancelled$(NC)"; \
	fi

.PHONY: test
test: ## Build and test the image locally
	@$(MAKE) build
	@echo -e "$(BLUE)Testing image...$(NC)"
	@docker run --rm $(FULL_IMAGE_NAME):$(IMAGE_TAG) action-server --version
	@echo -e "$(GREEN)✓ Image test passed$(NC)"

.PHONY: inspect
inspect: ## Show image details and layers
	@docker inspect $(FULL_IMAGE_NAME):$(IMAGE_TAG)

.PHONY: size
size: ## Show image size
	@docker images $(FULL_IMAGE_NAME):$(IMAGE_TAG) --format "table {{.Repository}}:{{.Tag}}\t{{.Size}}"

.PHONY: tag
tag: ## Tag image with new name (usage: make tag NEW_TAG=v1.0.0)
	@if [ -z "$(NEW_TAG)" ]; then \
		echo "$(RED)Error: NEW_TAG variable not set$(NC)"; \
		echo "$(YELLOW)Usage: make tag NEW_TAG=v1.0.0$(NC)"; \
		exit 1; \
	fi
	@echo -e "$(BLUE)Tagging image as $(FULL_IMAGE_NAME):$(NEW_TAG)$(NC)"
	docker tag $(FULL_IMAGE_NAME):$(IMAGE_TAG) $(FULL_IMAGE_NAME):$(NEW_TAG)
	@echo -e "$(GREEN)✓ Image tagged$(NC)"

.PHONY: all
all: clean build test ## Clean, build, and test

.PHONY: deploy
deploy: build push ## Build and push to registry
	@echo -e "$(GREEN)✓ Deployment complete$(NC)"

# Quick shortcuts
.PHONY: b p r
b: build ## Shortcut for build
p: push ## Shortcut for push
r: run ## Shortcut for run
