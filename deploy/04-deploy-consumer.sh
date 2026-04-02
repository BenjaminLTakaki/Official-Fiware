#!/usr/bin/env bash
# =============================================================================
# 04-deploy-consumer.sh
# Deploy the FIWARE Data Space Consumer (Keycloak + VCVerifier + TIL + CCS).
# Run AFTER 03-deploy-trust-anchor.sh.
# =============================================================================
set -euo pipefail
export KUBECONFIG=~/.kube/config

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KEYS_DIR="$SCRIPT_DIR/keys"

echo "========================================"
echo " Deploying Consumer"
echo "========================================"

# Ensure we have the consumer DID
if [[ ! -f "$KEYS_DIR/consumer.did" ]]; then
  echo "ERROR: $KEYS_DIR/consumer.did not found. Run 02-generate-identities.sh first."
  exit 1
fi

CONSUMER_DID=$(cat "$KEYS_DIR/consumer.did")
echo "Consumer DID: $CONSUMER_DID"

# Create the realm ConfigMap so Keycloak can import it on startup
echo ""
echo "[1/3] Creating Keycloak realm ConfigMap..."
kubectl create configmap keycloak-realm \
  --namespace consumer \
  --from-file=fiware-realm.json="$SCRIPT_DIR/realm/fiware-realm.json" \
  --dry-run=client -o yaml | kubectl apply -f -

# Deploy the consumer chart
echo ""
echo "[2/3] Installing consumer chart (this takes ~3 min for Keycloak to start)..."
helm upgrade --install consumer dsc/data-space-connector \
  --namespace consumer \
  --version 7.37.4 \
  --values "$SCRIPT_DIR/values/consumer.yaml" \
  --set "vcwaltid.app.vcVerifier.did=$CONSUMER_DID" \
  --timeout 15m \
  --wait

# Wait for all pods to be ready
echo ""
echo "[3/3] Waiting for all pods to be Ready..."
kubectl wait --for=condition=ready pod -n consumer --all --timeout=600s

echo ""
echo "========================================"
echo " Consumer deployed!"
echo ""
echo " Keycloak:      http://keycloak-consumer.127.0.1.1.nip.io"
echo "   Admin UI:    http://keycloak-consumer.127.0.1.1.nip.io/admin"
echo "   Admin creds: admin / admin-pass"
echo ""
echo " VCVerifier:    http://verifier-consumer.127.0.1.1.nip.io"
echo " TIL (local):   http://til-consumer.127.0.1.1.nip.io"
echo " CCS (local):   http://ccs-consumer.127.0.1.1.nip.io"
echo ""
echo " Test users (realm: fiware-server):"
echo "   test-reader   / test  (role: READER)"
echo "   test-operator / test  (role: OPERATOR)"
echo "========================================"
