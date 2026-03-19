# Beeper Demo Application Makefile
# Targets for deploying, managing, and tearing down the demo environment.

DEMO_NAMESPACE := beeper-demo
DEMO_IMAGE := beeper/demo-app:latest
DEMO_DIR := demo

.PHONY: demo-build demo-deploy demo-teardown demo-status demo-logs demo-fault demo-recover demo-fault-status demo-fault-list

## Build the demo application Docker image
demo-build:
	docker build -t $(DEMO_IMAGE) $(DEMO_DIR)/app/

## Deploy the demo application to Kubernetes
demo-deploy:
	@echo "==> Deploying demo application to namespace $(DEMO_NAMESPACE)..."
	kubectl apply -f $(DEMO_DIR)/k8s/namespace.yaml
	kubectl apply -f $(DEMO_DIR)/k8s/api-gateway.yaml
	kubectl apply -f $(DEMO_DIR)/k8s/backend.yaml
	kubectl apply -f $(DEMO_DIR)/k8s/database.yaml
	kubectl apply -f $(DEMO_DIR)/k8s/worker.yaml
	kubectl apply -f $(DEMO_DIR)/k8s/slo-api-gateway.yaml
	kubectl apply -f $(DEMO_DIR)/k8s/slo-backend.yaml
	kubectl apply -f $(DEMO_DIR)/k8s/slo-database.yaml
	kubectl apply -f $(DEMO_DIR)/k8s/slo-worker.yaml
	@echo "==> Waiting for rollout..."
	kubectl -n $(DEMO_NAMESPACE) rollout status deployment/demo-api-gateway --timeout=60s
	kubectl -n $(DEMO_NAMESPACE) rollout status deployment/demo-backend --timeout=60s
	kubectl -n $(DEMO_NAMESPACE) rollout status deployment/demo-database --timeout=60s
	kubectl -n $(DEMO_NAMESPACE) rollout status deployment/demo-worker --timeout=60s
	@echo "==> Demo application deployed successfully!"

## Tear down the demo application (deletes entire namespace)
demo-teardown:
	@echo "==> Tearing down demo application..."
	kubectl delete namespace $(DEMO_NAMESPACE) --ignore-not-found
	@echo "==> Demo application removed."

## Show demo application status
demo-status:
	@echo "==> Pod Status:"
	@kubectl -n $(DEMO_NAMESPACE) get pods -o wide 2>/dev/null || echo "  Namespace $(DEMO_NAMESPACE) not found"
	@echo ""
	@echo "==> Services:"
	@kubectl -n $(DEMO_NAMESPACE) get services 2>/dev/null || echo "  Namespace $(DEMO_NAMESPACE) not found"
	@echo ""
	@echo "==> ServiceLevels:"
	@kubectl -n $(DEMO_NAMESPACE) get servicelevels 2>/dev/null || echo "  No ServiceLevel CRDs found"

## Tail logs from all demo pods
demo-logs:
	kubectl -n $(DEMO_NAMESPACE) logs -l app.kubernetes.io/part-of=beeper-demo --all-containers --follow --prefix

## Inject a fault into a demo service
## Usage: make demo-fault TYPE=memory-leak SERVICE=backend
demo-fault:
	@test -n "$(TYPE)" || (echo "Error: TYPE is required (memory-leak, bad-deploy, cascading-failure, scale-dependent)" && exit 1)
	@test -n "$(SERVICE)" || (echo "Error: SERVICE is required (api-gateway, backend, database, worker)" && exit 1)
	@echo "==> Injecting fault '$(TYPE)' into $(SERVICE)..."
	@kubectl -n $(DEMO_NAMESPACE) exec deploy/demo-$(SERVICE) -- \
		wget -qO- --post-data='{"fault_type":"$(TYPE)"}' \
		--header='Content-Type: application/json' \
		http://localhost:8080/fault/inject 2>/dev/null || \
		kubectl -n $(DEMO_NAMESPACE) exec deploy/demo-$(SERVICE) -- \
		wget -qO- --post-data='{"fault_type":"$(TYPE)"}' \
		--header='Content-Type: application/json' \
		http://localhost:8081/fault/inject 2>/dev/null || \
		echo "  Failed to inject fault. Is the demo deployed?"
	@echo ""
	@echo "==> Fault injected. Monitor with: make demo-fault-status"

## Recover all services from fault injection
## Usage: make demo-recover [SERVICE=backend]
demo-recover:
	@echo "==> Recovering from fault injection..."
	@if [ -n "$(SERVICE)" ]; then \
		kubectl -n $(DEMO_NAMESPACE) exec deploy/demo-$(SERVICE) -- \
			wget -qO- --post-data='{}' \
			--header='Content-Type: application/json' \
			http://localhost:8080/fault/recover 2>/dev/null || \
			kubectl -n $(DEMO_NAMESPACE) exec deploy/demo-$(SERVICE) -- \
			wget -qO- --post-data='{}' \
			--header='Content-Type: application/json' \
			http://localhost:8081/fault/recover 2>/dev/null || \
			echo "  Failed to recover $(SERVICE)"; \
	else \
		for svc in api-gateway backend database worker; do \
			echo "  Recovering demo-$$svc..."; \
			kubectl -n $(DEMO_NAMESPACE) exec deploy/demo-$$svc -- \
				wget -qO- --post-data='{}' \
				--header='Content-Type: application/json' \
				http://localhost:8080/fault/recover 2>/dev/null || \
				kubectl -n $(DEMO_NAMESPACE) exec deploy/demo-$$svc -- \
				wget -qO- --post-data='{}' \
				--header='Content-Type: application/json' \
				http://localhost:8081/fault/recover 2>/dev/null || \
				echo "  Failed to recover $$svc"; \
		done; \
	fi
	@echo "==> Recovery complete."

## Show fault injection status across all services
demo-fault-status:
	@echo "==> Fault Injection Status:"
	@for svc in api-gateway backend database worker; do \
		echo ""; \
		echo "  $$svc:"; \
		kubectl -n $(DEMO_NAMESPACE) exec deploy/demo-$$svc -- \
			wget -qO- http://localhost:8080/fault/status 2>/dev/null || \
			kubectl -n $(DEMO_NAMESPACE) exec deploy/demo-$$svc -- \
			wget -qO- http://localhost:8081/fault/status 2>/dev/null || \
			echo "    unavailable"; \
	done

## List available fault types
demo-fault-list:
	@echo "==> Available Fault Types:"
	@echo ""
	@echo "  memory-leak       Gradual memory leak leading to OOM"
	@echo "  bad-deploy        HTTP 500 error rate spike (simulates broken deploy)"
	@echo "  cascading-failure Error propagation across dependent services"
	@echo "  scale-dependent   Latency increases with concurrent request count"
	@echo ""
	@echo "Usage: make demo-fault TYPE=<type> SERVICE=<service>"
	@echo "       make demo-recover [SERVICE=<service>]"
