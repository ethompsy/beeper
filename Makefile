# Beeper Demo Application Makefile
# Targets for deploying, managing, and tearing down the demo environment.

DEMO_NAMESPACE := beeper-demo
DEMO_IMAGE := beeper/demo-app:latest
DEMO_DIR := demo

.PHONY: demo-build demo-deploy demo-teardown demo-status demo-logs

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
