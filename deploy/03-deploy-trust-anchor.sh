#!/usr/bin/env bash
# =============================================================================
# 03-deploy-trust-anchor.sh
# Deploy the FIWARE Trust Anchor (TIL + CCS + MySQL).
# Run AFTER 01-prerequisites.sh and 02-generate-identities.sh.
# =============================================================================
set -euo pipefail
export KUBECONFIG=~/.kube/config

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "========================================"
echo " Deploying Trust Anchor"
echo "========================================"

# Ensure namespace exists
kubectl create namespace trust-anchor --dry-run=client -o yaml | kubectl apply -f -

# Deploy the trust anchor chart (version 0.2.0 — the lightweight TIL-only chart)
helm upgrade --install trust-anchor dsc/data-space-connector \
  --namespace trust-anchor \
  --version 0.2.0 \
  --values "$SCRIPT_DIR/values/trust-anchor.yaml" \
  --timeout 10m \
  --wait

echo ""
echo "Waiting for TIL and CCS to be fully ready..."
kubectl rollout status deployment -n trust-anchor --timeout=300s 2>/dev/null || true
kubectl wait --for=condition=ready pod -n trust-anchor --all --timeout=300s

echo ""
echo "========================================"
echo " Trust Anchor deployed!"
echo ""
echo " TIL endpoint:  http://til.127.0.1.1.nip.io"
echo " CCS endpoint:  http://ccs.127.0.1.1.nip.io"
echo ""
echo " Verify:"
echo "   curl http://til.127.0.1.1.nip.io/v4/issuers"
echo "========================================"
