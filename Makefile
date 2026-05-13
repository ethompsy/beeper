# Beeper + OTel Astronomy Shop Demo Makefile
#
# Deploys the OpenTelemetry Astronomy Shop as a real-world target application
# for Beeper to monitor, detect anomalies, and investigate root causes.
#
# Prerequisites:
#   - docker (for building images)
#   - helm 3.x installed
#   - For full K8s demo: kind (installed automatically by demo-cluster)
#   - For local LLM (Ollama): OLLAMA_HOST=0.0.0.0 ollama serve
#     (must bind all interfaces so kind pods can reach host.docker.internal)

DEMO_NAMESPACE := otel-demo
BEEPER_NAMESPACE := beeper
DEMO_RELEASE := otel-demo
BEEPER_RELEASE := beeper
DEMO_DIR := demo
HELM_CHART := open-telemetry/opentelemetry-demo
KIND_CLUSTER := beeper-demo
KIND_CONFIG := kind-config.yaml
BEEPER_TAG := dev

.PHONY: demo-up demo-down demo-cluster demo-build demo-beeper \
        demo-deploy demo-teardown demo-status demo-logs \
        demo-fault demo-recover demo-fault-status demo-fault-list \
        demo-ui demo-helm-repo \
        tailwind-watch tailwind-build

# ── Tailwind CSS ─────────────────────────────────────────────────────────────
# Requires: tailwindcss standalone CLI on PATH
#   Dev:    curl -sL -o /usr/local/bin/tailwindcss https://github.com/tailwindlabs/tailwindcss/releases/download/v4.3.0/tailwindcss-macos-arm64 && chmod +x /usr/local/bin/tailwindcss
#   Docker: downloaded automatically in Dockerfile build stage

## Watch mode for development (generates CSS on file changes)
tailwind-watch:
	tailwindcss --watch -i ui/beeper_ui/static/css/input.css -o ui/beeper_ui/static/css/tailwind.css

## Production build (minified CSS)
tailwind-build:
	tailwindcss --minify -i ui/beeper_ui/static/css/input.css -o ui/beeper_ui/static/css/tailwind.css

# ── One-command setup/teardown ───────────────────────────────────────────────

## Full demo setup: cluster + images + Beeper + OTel demo
demo-up: demo-cluster demo-build demo-helm-repo demo-beeper demo-deploy
	@echo ""
	@echo "============================================"
	@echo "  Beeper demo is ready!"
	@echo "  Run 'make demo-ui' to open the UIs."
	@echo "  Run 'make demo-fault FAULT=cart-failure' to inject a fault."
	@echo "============================================"
	@echo ""
	@echo "  NOTE: Detection needs ~10 minutes of log data flowing before"
	@echo "        anomalies can be detected. Wait before injecting faults."

## Delete the kind cluster entirely
demo-down:
	@echo "==> Deleting kind cluster '$(KIND_CLUSTER)'..."
	kind delete cluster --name $(KIND_CLUSTER) 2>/dev/null || true
	@echo "==> Cluster deleted."

# ── Cluster management ───────────────────────────────────────────────────────

## Create a kind cluster for the demo (installs kind if missing)
demo-cluster:
	@DOCKER_MEM=$$(docker info --format '{{.MemTotal}}' 2>/dev/null); \
	if [ -n "$$DOCKER_MEM" ]; then \
		DOCKER_MEM_GB=$$(echo "$$DOCKER_MEM" | awk '{printf "%.1f", $$1/1073741824}'); \
		DOCKER_MEM_INT=$$(echo "$$DOCKER_MEM" | awk '{printf "%d", $$1/1073741824}'); \
		if [ "$$DOCKER_MEM_INT" -lt 12 ]; then \
			echo ""; \
			echo "WARNING: Docker has $${DOCKER_MEM_GB}GB memory, but the demo needs ~12GB."; \
			echo "  Increase via: Docker Desktop → Settings → Resources → Memory → 12GB+"; \
			echo ""; \
		fi; \
	fi
	@if ! command -v kind &>/dev/null; then \
		echo "==> kind not found. Installing via Homebrew..."; \
		brew install kind; \
	fi
	@if kind get clusters 2>/dev/null | grep -q '^$(KIND_CLUSTER)$$'; then \
		echo "==> kind cluster '$(KIND_CLUSTER)' already exists."; \
	else \
		echo "==> Creating kind cluster '$(KIND_CLUSTER)'..."; \
		kind create cluster --name $(KIND_CLUSTER) --config $(KIND_CONFIG); \
	fi
	@kubectl cluster-info --context kind-$(KIND_CLUSTER) >/dev/null 2>&1 || \
		(echo "Error: kubectl context kind-$(KIND_CLUSTER) not working" && exit 1)
	@echo "==> Cluster ready."

## Build Docker images and load into kind
demo-build:
	@echo "==> Building Beeper Docker images (tag: $(BEEPER_TAG))..."
	docker build -t beeper/operator:$(BEEPER_TAG) ./operator
	docker build -t beeper/ui:$(BEEPER_TAG) ./ui
	docker build -t beeper/investigator:$(BEEPER_TAG) ./investigator
	@echo "==> Loading images into kind cluster '$(KIND_CLUSTER)'..."
	kind load docker-image beeper/operator:$(BEEPER_TAG) --name $(KIND_CLUSTER)
	kind load docker-image beeper/ui:$(BEEPER_TAG) --name $(KIND_CLUSTER)
	kind load docker-image beeper/investigator:$(BEEPER_TAG) --name $(KIND_CLUSTER)
	@echo "==> Images loaded."

# ── Beeper deployment ────────────────────────────────────────────────────────

## Deploy Beeper itself (operator, UI, Qdrant, CRDs) via Helm
demo-beeper:
	@echo "==> Creating namespace $(BEEPER_NAMESPACE)..."
	kubectl create namespace $(BEEPER_NAMESPACE) --dry-run=client -o yaml | kubectl apply -f -
	@# Create LLM credentials secret from ANTHROPIC_API_KEY or BEEPER_LLM_API_KEY
	@LLM_KEY="$${ANTHROPIC_API_KEY:-$${BEEPER_LLM_API_KEY:-}}"; \
	if [ -z "$$LLM_KEY" ]; then \
		echo ""; \
		echo "ERROR: ANTHROPIC_API_KEY (or BEEPER_LLM_API_KEY) must be set."; \
		echo "  Investigations require an LLM API key to complete."; \
		echo "  Export your key and re-run:"; \
		echo "    export ANTHROPIC_API_KEY=sk-ant-..."; \
		echo "    make demo-up"; \
		echo ""; \
		echo "  Without an API key, SLO monitoring and fault injection still work,"; \
		echo "  but investigator jobs will fail."; \
		exit 1; \
	fi; \
	echo "==> Creating LLM credentials secret..."; \
	kubectl create secret generic llm-credentials \
		--namespace $(BEEPER_NAMESPACE) \
		--from-literal=api-key="$$LLM_KEY" \
		--dry-run=client -o yaml | kubectl apply -f -
	@echo "==> Installing Beeper Helm chart..."
	helm upgrade --install $(BEEPER_RELEASE) ./helm/beeper \
		--namespace $(BEEPER_NAMESPACE) \
		--values ./helm/beeper/values-dev.yaml \
		--set operator.image.tag=$(BEEPER_TAG) \
		--set ui.image.tag=$(BEEPER_TAG) \
		--set investigator.image.tag=$(BEEPER_TAG) \
		--timeout 5m \
		--wait
	@echo "==> Beeper deployed."

# ── OTel demo deployment ────────────────────────────────────────────────────

## Add the OTel Helm chart repo (run once)
demo-helm-repo:
	@echo "==> Adding OpenTelemetry Helm chart repo..."
	helm repo add open-telemetry https://open-telemetry.github.io/opentelemetry-helm-charts 2>/dev/null || true
	helm repo update
	@echo "==> Helm repo ready."

## Deploy the OTel Astronomy Shop + Beeper SLOs
demo-deploy:
	@echo "==> Checking for Beeper CRDs..."
	@kubectl get crd servicelevels.beeper.dev >/dev/null 2>&1 || \
		(echo "Error: ServiceLevel CRD not found. Run 'make demo-beeper' first." && exit 1)
	@echo "==> Creating namespace $(DEMO_NAMESPACE)..."
	kubectl create namespace $(DEMO_NAMESPACE) --dry-run=client -o yaml | kubectl apply -f -
	@echo "==> Installing OTel Astronomy Shop via Helm..."
	helm upgrade --install $(DEMO_RELEASE) $(HELM_CHART) \
		--namespace $(DEMO_NAMESPACE) \
		--values $(DEMO_DIR)/otel-demo-values.yaml \
		--timeout 10m \
		--wait
	@echo "==> Initializing Qdrant collections..."
	kubectl -n $(BEEPER_NAMESPACE) port-forward svc/beeper-qdrant 6333:6333 &
	sleep 2
	python3 scripts/init-collections.py --host localhost --port 6333
	python3 scripts/seed_kb.py --host localhost --port 6333
	kill %1 2>/dev/null || true
	@echo "==> Applying ServiceLevel CRDs..."
	kubectl apply -f $(DEMO_DIR)/k8s/slo-checkout.yaml
	kubectl apply -f $(DEMO_DIR)/k8s/slo-cart.yaml
	kubectl apply -f $(DEMO_DIR)/k8s/slo-frontend.yaml
	kubectl apply -f $(DEMO_DIR)/k8s/slo-productcatalog.yaml
	@echo "==> Applying Source CRD..."
	kubectl apply -f $(DEMO_DIR)/k8s/source-prometheus.yaml
	@echo ""
	@echo "==> Demo deployed! Run 'make demo-status' to check pods."
	@echo "    Run 'make demo-ui' to port-forward the UIs."

## Tear down the demo (deletes namespace + Beeper release)
demo-teardown:
	@echo "==> Uninstalling OTel demo Helm release..."
	helm uninstall $(DEMO_RELEASE) --namespace $(DEMO_NAMESPACE) 2>/dev/null || true
	@echo "==> Deleting namespace $(DEMO_NAMESPACE)..."
	kubectl delete namespace $(DEMO_NAMESPACE) --ignore-not-found
	@echo "==> Cleaning up Source CRD..."
	kubectl delete -f $(DEMO_DIR)/k8s/source-prometheus.yaml --ignore-not-found 2>/dev/null || true
	@echo "==> Uninstalling Beeper Helm release..."
	helm uninstall $(BEEPER_RELEASE) --namespace $(BEEPER_NAMESPACE) 2>/dev/null || true
	kubectl delete namespace $(BEEPER_NAMESPACE) --ignore-not-found
	@echo "==> Demo removed."

## Show demo pod/service status
demo-status:
	@echo "==> Beeper Pods ($(BEEPER_NAMESPACE)):"
	@kubectl -n $(BEEPER_NAMESPACE) get pods 2>/dev/null || echo "  Namespace $(BEEPER_NAMESPACE) not found"
	@echo ""
	@echo "==> OTel Demo Pods ($(DEMO_NAMESPACE)):"
	@kubectl -n $(DEMO_NAMESPACE) get pods 2>/dev/null || echo "  Namespace $(DEMO_NAMESPACE) not found"
	@echo ""
	@echo "==> Services:"
	@kubectl -n $(DEMO_NAMESPACE) get services 2>/dev/null || echo "  Namespace $(DEMO_NAMESPACE) not found"
	@echo ""
	@echo "==> ServiceLevels:"
	@kubectl -n $(DEMO_NAMESPACE) get servicelevels 2>/dev/null || echo "  No ServiceLevel CRDs found"
	@echo ""
	@echo "==> Sources ($(BEEPER_NAMESPACE)):"
	@kubectl -n $(BEEPER_NAMESPACE) get sources 2>/dev/null || echo "  No Source CRDs found"

## Tail logs from demo pods
demo-logs:
	kubectl -n $(DEMO_NAMESPACE) logs -l app.kubernetes.io/instance=$(DEMO_RELEASE) --all-containers --follow --prefix --max-log-requests=20

## Inject a fault via feature flag
## Usage: make demo-fault FAULT=payment-failure
demo-fault:
	@test -n "$(FAULT)" || (echo "Error: FAULT is required. Run 'make demo-fault-list' for options." && exit 1)
	@echo "==> Enabling fault '$(FAULT)'..."
	@case "$(FAULT)" in \
		payment-failure) FLAG_KEY=paymentFailure; ON_VARIANT='100%%' ;; \
		cart-failure)    FLAG_KEY=cartFailure;    ON_VARIANT=on ;; \
		kafka-problems)  FLAG_KEY=kafkaQueueProblems; ON_VARIANT=on ;; \
		slow-images)     FLAG_KEY=imageSlowLoad;  ON_VARIANT=on ;; \
		high-cpu)        FLAG_KEY=adHighCpu;      ON_VARIANT=on ;; \
		*) echo "Error: Unknown fault '$(FAULT)'. Run 'make demo-fault-list' for options." && exit 1 ;; \
	esac && \
	kubectl -n $(DEMO_NAMESPACE) get configmap flagd-config -o json | \
		python3 -c "import sys,json; \
cm=json.load(sys.stdin); \
flags=json.loads(cm['data']['demo.flagd.json']); \
flags['flags']['$$FLAG_KEY']['state']='ENABLED'; \
flags['flags']['$$FLAG_KEY']['defaultVariant']='$$ON_VARIANT'; \
cm['data']['demo.flagd.json']=json.dumps(flags); \
json.dump(cm,sys.stdout)" | \
		kubectl apply -f - && \
	kubectl -n $(DEMO_NAMESPACE) rollout restart deploy/flagd
	@echo "==> Fault '$(FAULT)' enabled. The load generator will trigger failures."
	@echo "    Monitor with: make demo-fault-status"
	@echo "    NOTE: Detection needs ~10 minutes of baseline log data before"
	@echo "          anomalies can be detected (applies after demo-up or operator restart)."

## Recover from all fault injection (reset feature flags)
demo-recover:
	@echo "==> Resetting all feature flags to defaults..."
	@kubectl -n $(DEMO_NAMESPACE) get configmap flagd-config -o json | \
		python3 -c "exec(\"import sys,json\ncm=json.load(sys.stdin)\nflags=json.loads(cm['data']['demo.flagd.json'])\nfor f in flags.get('flags',{}).values():\n    f['state']='DISABLED'\n    f['defaultVariant']='off'\ncm['data']['demo.flagd.json']=json.dumps(flags)\njson.dump(cm,sys.stdout)\")" | \
		kubectl apply -f -
	@kubectl -n $(DEMO_NAMESPACE) rollout restart deploy/flagd
	@echo "==> All faults cleared. Services will recover shortly."

## Show current feature flag (fault injection) status
demo-fault-status:
	@echo "==> Feature Flag Status:"
	@kubectl -n $(DEMO_NAMESPACE) get configmap flagd-config -o json 2>/dev/null | \
		python3 -c "exec(\"import sys,json\ncm=json.load(sys.stdin)\nflags=json.loads(cm['data']['demo.flagd.json'])\nprint()\nfor name,cfg in sorted(flags.get('flags',{}).items()):\n    state=cfg.get('state','DISABLED')\n    default=cfg.get('defaultVariant','off')\n    marker='ON' if state=='ENABLED' and default!='off' else 'off'\n    print(f'  {name:30s} [{marker}]')\")" \
		|| echo "  Could not read flagd config. Is the demo deployed?"

## List available faults
demo-fault-list:
	@echo "==> Available Faults (OTel Astronomy Shop feature flags):"
	@echo ""
	@echo "  payment-failure   Payment service charge method errors"
	@echo "  cart-failure      Cart service EmptyCart failures"
	@echo "  kafka-problems    Kafka queue overload + consumer delays"
	@echo "  slow-images       Deliberate image loading delays"
	@echo "  high-cpu          Ad service high CPU consumption"
	@echo ""
	@echo "Usage: make demo-fault FAULT=<name>"
	@echo "       make demo-recover"
	@echo "       make demo-fault-status"

## Port-forward UIs for local access
demo-ui:
	@echo "==> Port-forwarding demo UIs..."
	@echo ""
	@echo "  Beeper UI:       http://localhost:5050"
	@echo "  OTel Shop:       http://localhost:8080"
	@echo "  Feature Flags:   http://localhost:8080/feature"
	@echo "  Jaeger:          http://localhost:16686"
	@echo ""
	@echo "Press Ctrl+C to stop."
	@echo ""
	@kubectl -n $(DEMO_NAMESPACE) port-forward svc/frontend-proxy 8080:8080 &
	@kubectl -n $(DEMO_NAMESPACE) port-forward svc/jaeger 16686:16686 &
	@kubectl -n $(BEEPER_NAMESPACE) port-forward svc/beeper-ui 5050:80 2>/dev/null &
	@wait
