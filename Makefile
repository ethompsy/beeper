# Beeper Demo Application Makefile
# Targets for deploying, managing, and tearing down the demo environment.

DEMO_NAMESPACE := beeper-demo
DEMO_IMAGE := beeper/demo-app:latest
DEMO_DIR := demo

.PHONY: demo-build demo-deploy demo-teardown demo-status demo-logs demo-fault demo-recover demo-fault-status demo-fault-list demo-lifecycle demo-lifecycle-status demo-lifecycle-reset demo-lifecycle-timeline demo-scenario demo-list demo-all

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

## Start a full lifecycle demonstration
## Usage: make demo-lifecycle FAULT=memory-leak [SERVICE=backend] [TRUST=5]
demo-lifecycle:
	@test -n "$(FAULT)" || (echo "Error: FAULT is required (memory-leak, bad-deploy, cascading-failure, scale-dependent)" && exit 1)
	$(eval LIFECYCLE_SERVICE := $(or $(SERVICE),backend))
	$(eval LIFECYCLE_TRUST := $(or $(TRUST),5))
	@echo "==> Starting full lifecycle demo: fault=$(FAULT), service=$(LIFECYCLE_SERVICE), trust_level=$(LIFECYCLE_TRUST)..."
	@kubectl -n $(DEMO_NAMESPACE) exec deploy/demo-$(LIFECYCLE_SERVICE) -- \
		wget -qO- --post-data='{"fault_type":"$(FAULT)","trust_level":$(LIFECYCLE_TRUST)}' \
		--header='Content-Type: application/json' \
		http://localhost:8080/lifecycle/start 2>/dev/null || \
		kubectl -n $(DEMO_NAMESPACE) exec deploy/demo-$(LIFECYCLE_SERVICE) -- \
		wget -qO- --post-data='{"fault_type":"$(FAULT)","trust_level":$(LIFECYCLE_TRUST)}' \
		--header='Content-Type: application/json' \
		http://localhost:8081/lifecycle/start 2>/dev/null || \
		echo "  Failed to start lifecycle. Is the demo deployed?"
	@echo ""
	@echo "==> Lifecycle started. Monitor with: make demo-lifecycle-status"

## Show lifecycle demonstration status
## Usage: make demo-lifecycle-status [SERVICE=backend]
demo-lifecycle-status:
	$(eval LIFECYCLE_SERVICE := $(or $(SERVICE),backend))
	@echo "==> Lifecycle Status ($(LIFECYCLE_SERVICE)):"
	@kubectl -n $(DEMO_NAMESPACE) exec deploy/demo-$(LIFECYCLE_SERVICE) -- \
		wget -qO- http://localhost:8080/lifecycle/status 2>/dev/null || \
		kubectl -n $(DEMO_NAMESPACE) exec deploy/demo-$(LIFECYCLE_SERVICE) -- \
		wget -qO- http://localhost:8081/lifecycle/status 2>/dev/null || \
		echo "  unavailable"

## Reset lifecycle demonstration
## Usage: make demo-lifecycle-reset [SERVICE=backend]
demo-lifecycle-reset:
	$(eval LIFECYCLE_SERVICE := $(or $(SERVICE),backend))
	@echo "==> Resetting lifecycle on $(LIFECYCLE_SERVICE)..."
	@kubectl -n $(DEMO_NAMESPACE) exec deploy/demo-$(LIFECYCLE_SERVICE) -- \
		wget -qO- --post-data='{}' \
		--header='Content-Type: application/json' \
		http://localhost:8080/lifecycle/reset 2>/dev/null || \
		kubectl -n $(DEMO_NAMESPACE) exec deploy/demo-$(LIFECYCLE_SERVICE) -- \
		wget -qO- --post-data='{}' \
		--header='Content-Type: application/json' \
		http://localhost:8081/lifecycle/reset 2>/dev/null || \
		echo "  Failed to reset lifecycle."
	@echo ""
	@echo "==> Lifecycle reset complete."

## Show full lifecycle timeline with narration
## Usage: make demo-lifecycle-timeline [SERVICE=backend]
demo-lifecycle-timeline:
	$(eval LIFECYCLE_SERVICE := $(or $(SERVICE),backend))
	@echo "==> Lifecycle Timeline ($(LIFECYCLE_SERVICE)):"
	@kubectl -n $(DEMO_NAMESPACE) exec deploy/demo-$(LIFECYCLE_SERVICE) -- \
		wget -qO- http://localhost:8080/lifecycle/timeline 2>/dev/null || \
		kubectl -n $(DEMO_NAMESPACE) exec deploy/demo-$(LIFECYCLE_SERVICE) -- \
		wget -qO- http://localhost:8081/lifecycle/timeline 2>/dev/null || \
		echo "  unavailable"

## Run a scripted demo scenario
## Usage: make demo-scenario SCENARIO=memory-leak [SERVICE=backend]
demo-scenario:
	@test -n "$(SCENARIO)" || (echo "Error: SCENARIO is required (memory-leak, bad-deploy, cascading-failure, scale-dependent)" && exit 1)
	$(eval SCENARIO_SERVICE := $(or $(SERVICE),backend))
	@echo "==> Running demo scenario '$(SCENARIO)' on $(SCENARIO_SERVICE)..."
	@kubectl -n $(DEMO_NAMESPACE) exec deploy/demo-$(SCENARIO_SERVICE) -- \
		wget -qO- --post-data='{"scenario":"$(SCENARIO)"}' \
		--header='Content-Type: application/json' \
		http://localhost:8080/scenarios/run 2>/dev/null || \
		kubectl -n $(DEMO_NAMESPACE) exec deploy/demo-$(SCENARIO_SERVICE) -- \
		wget -qO- --post-data='{"scenario":"$(SCENARIO)"}' \
		--header='Content-Type: application/json' \
		http://localhost:8081/scenarios/run 2>/dev/null || \
		echo "  Failed to run scenario. Is the demo deployed?"
	@echo ""
	@echo "==> Scenario complete. Check results with: make demo-scenario-status"

## List available demo scenarios
demo-list:
	@echo "==> Available Demo Scenarios:"
	@echo ""
	@echo "  memory-leak          Gradual memory leak → OOM detection & remediation         (~53s)"
	@echo "  bad-deploy           Broken deploy → error rate spike → rollback proposal      (~42s)"
	@echo "  cascading-failure    Cascading failure → dependency tracing → root cause fix   (~62s)"
	@echo "  scale-dependent      Load-triggered latency → SLO burn rate → HPA scaling     (~53s)"
	@echo ""
	@echo "Usage: make demo-scenario SCENARIO=<name> [SERVICE=backend]"
	@echo "       make demo-all [SERVICE=backend]"

## Run all demo scenarios in sequence
## Usage: make demo-all [SERVICE=backend]
demo-all:
	$(eval SCENARIO_SERVICE := $(or $(SERVICE),backend))
	@echo "==> Running all demo scenarios on $(SCENARIO_SERVICE)..."
	@kubectl -n $(DEMO_NAMESPACE) exec deploy/demo-$(SCENARIO_SERVICE) -- \
		wget -qO- --post-data='{}' \
		--header='Content-Type: application/json' \
		http://localhost:8080/scenarios/run-all 2>/dev/null || \
		kubectl -n $(DEMO_NAMESPACE) exec deploy/demo-$(SCENARIO_SERVICE) -- \
		wget -qO- --post-data='{}' \
		--header='Content-Type: application/json' \
		http://localhost:8081/scenarios/run-all 2>/dev/null || \
		echo "  Failed to run scenarios. Is the demo deployed?"
	@echo ""
	@echo "==> All scenarios complete."
