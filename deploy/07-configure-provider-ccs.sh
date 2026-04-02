#!/usr/bin/env bash
# =============================================================================
# 07-configure-provider-ccs.sh
# Register the OperatorCredential type in the Provider's Credential Config
# Service (CCS). This tells the VCVerifier which credential types to accept.
# Run AFTER 06-register-participants.sh.
# =============================================================================
set -euo pipefail
export KUBECONFIG=~/.kube/config

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KEYS_DIR="$SCRIPT_DIR/keys"

PROVIDER_CCS_URL="http://ccs-provider.127.0.1.1.nip.io"
PROVIDER_VERIFIER_URL="http://verifier-provider.127.0.1.1.nip.io"

echo "========================================"
echo " Configuring Provider Credential Config Service"
echo "========================================"

PROVIDER_DID=$(cat "$KEYS_DIR/provider.did")

# Wait for CCS to be available
echo "Waiting for Provider CCS..."
for i in {1..20}; do
  if curl -sf "$PROVIDER_CCS_URL" &>/dev/null || curl -sf "$PROVIDER_CCS_URL/v1/services" &>/dev/null; then
    echo "  Provider CCS is reachable."
    break
  fi
  echo "  Waiting... ($i/20)"
  sleep 10
done

# Register the OperatorCredential service in CCS
# This tells the VCVerifier: "For service 'provider', accept OperatorCredential
# tokens that were verified against the Trust Anchor TIL."
echo ""
echo "Registering OperatorCredential in Provider CCS..."

curl -sf -X POST "$PROVIDER_CCS_URL/v1/services" \
  -H "Content-Type: application/json" \
  -d "{
    \"id\": \"provider\",
    \"defaultOidcScope\": \"operator\",
    \"oidcScopes\": {
      \"operator\": [
        {
          \"type\": \"OperatorCredential\",
          \"trustedParticipantsLists\": [
            {
              \"url\": \"http://til.127.0.1.1.nip.io\",
              \"type\": \"ebsi\",
              \"prefix\": \"\"
            }
          ],
          \"trustedIssuersLists\": [
            {
              \"url\": \"http://til.127.0.1.1.nip.io\"
            }
          ]
        }
      ]
    }
  }" && echo "  CCS configured." || echo "  CCS configuration failed (may already exist)."

echo ""
echo "========================================"
echo " Provider CCS configured!"
echo ""
echo " Verify:"
echo "   curl $PROVIDER_CCS_URL/v1/services | jq ."
echo "========================================"
