#!/usr/bin/env bash
# =============================================================================
# 06-register-participants.sh
# Register Consumer and Provider DIDs in the Trust Anchor's TIL.
# Also registers Consumer's DID in the Provider's local TIL with allowed credential types.
# Run AFTER 05-deploy-provider.sh.
# =============================================================================
set -euo pipefail
export KUBECONFIG=~/.kube/config

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KEYS_DIR="$SCRIPT_DIR/keys"

TIL_URL="http://til.127.0.1.1.nip.io"
PROVIDER_TIL_URL="http://til-provider.127.0.1.1.nip.io"

echo "========================================"
echo " Registering participants in TIL"
echo "========================================"

# Load DIDs
CONSUMER_DID=$(cat "$KEYS_DIR/consumer.did")
PROVIDER_DID=$(cat "$KEYS_DIR/provider.did")

echo "Consumer DID: $CONSUMER_DID"
echo "Provider DID: $PROVIDER_DID"

# Wait for Trust Anchor TIL to be reachable
echo ""
echo "Waiting for Trust Anchor TIL to respond..."
for i in {1..30}; do
  if curl -sf "$TIL_URL/health" &>/dev/null || curl -sf "$TIL_URL/v4/issuers" &>/dev/null; then
    echo "TIL is reachable."
    break
  fi
  echo "  Waiting... ($i/30)"
  sleep 10
done

# ---------------------------------------------------------------------------
# Register CONSUMER in the global Trust Anchor TIL
# ---------------------------------------------------------------------------
echo ""
echo "[1/3] Registering Consumer DID in Trust Anchor TIL..."

curl -sf -X POST "$TIL_URL/v4/issuers" \
  -H "Content-Type: application/json" \
  -d "{
    \"did\": \"$CONSUMER_DID\",
    \"credentials\": [
      {
        \"validFor\": {
          \"from\": \"2024-01-01T00:00:00Z\",
          \"to\":   \"2034-01-01T00:00:00Z\"
        },
        \"credentialsType\": \"OperatorCredential\"
      }
    ]
  }" && echo "  Consumer registered in Trust Anchor TIL." || echo "  NOTE: Registration may already exist (409 = OK)."

# ---------------------------------------------------------------------------
# Register PROVIDER in the global Trust Anchor TIL
# ---------------------------------------------------------------------------
echo ""
echo "[2/3] Registering Provider DID in Trust Anchor TIL..."

curl -sf -X POST "$TIL_URL/v4/issuers" \
  -H "Content-Type: application/json" \
  -d "{
    \"did\": \"$PROVIDER_DID\",
    \"credentials\": [
      {
        \"validFor\": {
          \"from\": \"2024-01-01T00:00:00Z\",
          \"to\":   \"2034-01-01T00:00:00Z\"
        },
        \"credentialsType\": \"OperatorCredential\"
      }
    ]
  }" && echo "  Provider registered in Trust Anchor TIL." || echo "  NOTE: Registration may already exist (409 = OK)."

# ---------------------------------------------------------------------------
# Register CONSUMER in the PROVIDER'S LOCAL TIL
# (This tells the Provider that the Consumer is allowed to present OperatorCredential)
# ---------------------------------------------------------------------------
echo ""
echo "[3/3] Registering Consumer DID in Provider's local TIL..."

# Wait for Provider TIL to be reachable
for i in {1..20}; do
  if curl -sf "$PROVIDER_TIL_URL/health" &>/dev/null || curl -sf "$PROVIDER_TIL_URL/v4/issuers" &>/dev/null; then
    echo "  Provider TIL is reachable."
    break
  fi
  echo "  Waiting for Provider TIL... ($i/20)"
  sleep 10
done

curl -sf -X POST "$PROVIDER_TIL_URL/v4/issuers" \
  -H "Content-Type: application/json" \
  -d "{
    \"did\": \"$CONSUMER_DID\",
    \"credentials\": [
      {
        \"validFor\": {
          \"from\": \"2024-01-01T00:00:00Z\",
          \"to\":   \"2034-01-01T00:00:00Z\"
        },
        \"credentialsType\": \"OperatorCredential\"
      }
    ]
  }" && echo "  Consumer registered in Provider's TIL." || echo "  NOTE: May already exist."

echo ""
echo "========================================"
echo " Participant registration complete!"
echo ""
echo " Verify registrations:"
echo "   # List all issuers in Trust Anchor:"
echo "   curl http://til.127.0.1.1.nip.io/v4/issuers | jq ."
echo ""
echo "   # List issuers in Provider's TIL:"
echo "   curl http://til-provider.127.0.1.1.nip.io/v4/issuers | jq ."
echo "========================================"
