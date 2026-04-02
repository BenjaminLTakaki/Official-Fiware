#!/usr/bin/env bash
# =============================================================================
# 02-generate-identities.sh
# Generate EC P-256 keys, self-signed certificates, PKCS12 keystores, and
# did:key DIDs for the Consumer and Provider organisations.
# Creates Kubernetes secrets in each namespace.
# =============================================================================
set -euo pipefail
export KUBECONFIG=~/.kube/config

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KEYS_DIR="$SCRIPT_DIR/keys"
mkdir -p "$KEYS_DIR"

echo "========================================"
echo " Generating Consumer and Provider identities"
echo "========================================"

# --- Helper: generate identity for one participant ---
generate_identity() {
  local NAME="$1"          # e.g. "consumer" or "provider"
  local NAMESPACE="$2"     # k8s namespace
  local SECRET_NAME="$3"   # k8s secret name
  local PASSWORD="$4"      # PKCS12 keystore password

  local KEY="$KEYS_DIR/${NAME}.key"
  local CERT="$KEYS_DIR/${NAME}.crt"
  local P12="$KEYS_DIR/${NAME}.p12"
  local DID_FILE="$KEYS_DIR/${NAME}.did"

  echo ""
  echo "--- Generating identity for: $NAME ---"

  # 1. Generate EC P-256 private key
  openssl ecparam -name prime256v1 -genkey -noout -out "$KEY"
  echo "    [OK] Private key: $KEY"

  # 2. Create self-signed certificate (10-year validity)
  openssl req -new -x509 \
    -key "$KEY" \
    -out "$CERT" \
    -days 3650 \
    -subj "/CN=${NAME}/O=FIWARE DSC Demo/C=DE"
  echo "    [OK] Certificate: $CERT"

  # 3. Package into PKCS12 keystore
  openssl pkcs12 -export \
    -in "$CERT" \
    -inkey "$KEY" \
    -out "$P12" \
    -passout "pass:${PASSWORD}" \
    -name "$NAME"
  echo "    [OK] Keystore: $P12"

  # 4. Derive did:key from the keystore
  local DID
  DID=$(python3 "$SCRIPT_DIR/did_helper.py" "$P12" "$PASSWORD")
  echo "$DID" > "$DID_FILE"
  echo "    [OK] DID: $DID"

  # 5. Create Kubernetes namespace (ignore if exists)
  kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -

  # 6. Upload PKCS12 as a Kubernetes secret
  kubectl create secret generic "$SECRET_NAME" \
    --namespace "$NAMESPACE" \
    --from-file="keystore.p12=$P12" \
    --from-literal="password=$PASSWORD" \
    --dry-run=client -o yaml | kubectl apply -f -
  echo "    [OK] Secret '$SECRET_NAME' created in namespace '$NAMESPACE'"
}

# --- Consumer identity ---
generate_identity "consumer" "consumer" "consumer-identity" "consumer-keystore-pass"

# --- Provider identity ---
generate_identity "provider" "provider" "provider-identity" "provider-keystore-pass"

# --- Trust Anchor namespace ---
kubectl create namespace trust-anchor --dry-run=client -o yaml | kubectl apply -f -

# --- Print summary ---
echo ""
echo "========================================"
echo " Identity generation complete!"
echo ""
echo " Consumer DID: $(cat "$KEYS_DIR/consumer.did")"
echo " Provider DID: $(cat "$KEYS_DIR/provider.did")"
echo ""
echo " These DIDs will be:"
echo "  - Registered in the Trust Anchor TIL (script 04)"
echo "  - Configured in the Consumer/Provider Helm values"
echo ""
echo " IMPORTANT: Copy the DIDs above — they are needed in later steps."
echo " They are also saved to:"
echo "   $KEYS_DIR/consumer.did"
echo "   $KEYS_DIR/provider.did"
echo "========================================"
