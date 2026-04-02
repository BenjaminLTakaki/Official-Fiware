#!/usr/bin/env bash
# =============================================================================
# 05-deploy-provider.sh
# Deploy the FIWARE Data Space Provider (APISIX + OPA + Scorpio + ODRL PAP + TIL + CCS).
# Run AFTER 04-deploy-consumer.sh.
# =============================================================================
set -euo pipefail
export KUBECONFIG=~/.kube/config

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KEYS_DIR="$SCRIPT_DIR/keys"

echo "========================================"
echo " Deploying Provider"
echo "========================================"

# Ensure we have the provider DID
if [[ ! -f "$KEYS_DIR/provider.did" ]]; then
  echo "ERROR: $KEYS_DIR/provider.did not found. Run 02-generate-identities.sh first."
  exit 1
fi

PROVIDER_DID=$(cat "$KEYS_DIR/provider.did")
echo "Provider DID: $PROVIDER_DID"

# Deploy the provider chart
echo ""
echo "Installing provider chart (takes ~5 min — Scorpio is heavy)..."
helm upgrade --install provider dsc/data-space-connector \
  --namespace provider \
  --version 7.37.4 \
  --values "$SCRIPT_DIR/values/provider.yaml" \
  --set "vcwaltid.app.vcVerifier.did=$PROVIDER_DID" \
  --timeout 20m \
  --wait

# Wait for all pods to be ready
echo ""
echo "Waiting for all pods to be Ready..."
kubectl wait --for=condition=ready pod -n provider --all --timeout=900s

echo ""
echo "========================================"
echo " Provider deployed!"
echo ""
echo " Data endpoint:  http://provider.127.0.1.1.nip.io/ngsi-ld/v1/entities"
echo "   (protected — requires a valid VC token)"
echo " VCVerifier:     http://verifier-provider.127.0.1.1.nip.io"
echo " TIL (local):    http://til-provider.127.0.1.1.nip.io"
echo " CCS (local):    http://ccs-provider.127.0.1.1.nip.io"
echo " ODRL PAP:       http://pap-provider.127.0.1.1.nip.io"
echo " TM Forum APIs:  http://tmf-provider.127.0.1.1.nip.io"
echo "========================================"
