#!/usr/bin/env bash
# =============================================================================
# 08-create-odrl-policy.sh
# Create an ODRL access policy on the Provider that permits holders of an
# OperatorCredential with role READER or OPERATOR to access NGSI-LD entities.
# Run AFTER 07-configure-provider-ccs.sh.
# =============================================================================
set -euo pipefail
export KUBECONFIG=~/.kube/config

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KEYS_DIR="$SCRIPT_DIR/keys"

PAP_URL="http://pap-provider.127.0.1.1.nip.io"

echo "========================================"
echo " Creating ODRL Access Policy"
echo "========================================"

CONSUMER_DID=$(cat "$KEYS_DIR/consumer.did")

# Wait for ODRL PAP to be reachable
echo "Waiting for ODRL PAP..."
for i in {1..20}; do
  if curl -sf "$PAP_URL" &>/dev/null || curl -sf "$PAP_URL/policy" &>/dev/null; then
    echo "  ODRL PAP is reachable."
    break
  fi
  echo "  Waiting... ($i/20)"
  sleep 10
done

echo ""
echo "Creating ODRL policy for OperatorCredential holders..."

# Create an ODRL policy that permits GET on /ngsi-ld/v1/entities for anyone
# with a valid OperatorCredential (READER role).
# Once this policy exists: 401 → 403 → 200 flow will work completely.
curl -sf -X POST "$PAP_URL/policy" \
  -H "Content-Type: application/json" \
  -d '{
    "@context": {
      "dc": "http://purl.org/dc/elements/1.1/",
      "dct": "http://purl.org/dc/terms/",
      "owl": "http://www.w3.org/2002/07/owl#",
      "odrl": "http://www.w3.org/ns/odrl/2/",
      "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
      "skos": "http://www.w3.org/2004/02/skos/core#"
    },
    "@type": "odrl:Policy",
    "@id": "urn:policy:allow-operator-credential-read",
    "odrl:permission": [
      {
        "odrl:assigner": {
          "@id": "PROVIDER"
        },
        "odrl:target": {
          "@type": "odrl:AssetCollection",
          "@id": "urn:asset:ngsi-ld-entities",
          "odrl:source": "urn:asset:ngsi-ld-entities",
          "odrl:refinement": {
            "@type": "odrl:Constraint",
            "odrl:leftOperand": "ngsi-ld:EntityType",
            "odrl:operator": {"@id": "odrl:isAnyOf"},
            "odrl:rightOperand": "urn:ngsi-ld:EntityType:All"
          }
        },
        "odrl:action": {
          "@id": "odrl:read"
        },
        "odrl:constraint": [
          {
            "@type": "odrl:Constraint",
            "odrl:leftOperand": "vc:type",
            "odrl:operator": {"@id": "odrl:eq"},
            "odrl:rightOperand": "OperatorCredential"
          },
          {
            "@type": "odrl:Constraint",
            "odrl:leftOperand": "vc:role",
            "odrl:operator": {"@id": "odrl:isAnyOf"},
            "odrl:rightOperand": ["READER", "OPERATOR"]
          }
        ]
      }
    ]
  }' && echo "  ODRL policy created." || echo "  NOTE: Policy may already exist."

echo ""
echo "========================================"
echo " ODRL policy created!"
echo ""
echo " With this policy in place, the full 401 → 403 → 200 flow should now work."
echo " Run 09-test.sh to verify end-to-end."
echo "========================================"
