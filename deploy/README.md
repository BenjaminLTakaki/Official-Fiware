# FIWARE Data Space Connector — Complete Local Deployment

This folder contains everything needed to deploy a fully local FIWARE Data Space
with Consumer and Provider on a single Ubuntu machine using k3s (lightweight Kubernetes).

No cloud, no external DNS, no API keys required.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      k3s Cluster                            │
│                                                             │
│  Namespace: trust-anchor                                    │
│  ┌─────────────────────────────────────────┐                │
│  │  MySQL + TIL + CCS                      │                │
│  │  til.127.0.1.1.nip.io                   │                │
│  └─────────────────────────────────────────┘                │
│                         ▲                                   │
│          (both Consumer and Provider check TIL)             │
│                                                             │
│  Namespace: consumer                                        │
│  ┌─────────────────────────────────────────┐                │
│  │  Keycloak (OID4VC) + PostgreSQL         │                │
│  │  keycloak-consumer.127.0.1.1.nip.io     │                │
│  │  VCVerifier + local TIL + local CCS     │                │
│  └─────────────────────────────────────────┘                │
│                         │                                   │
│          (Consumer gets VC, presents to Provider)           │
│                         ▼                                   │
│  Namespace: provider                                        │
│  ┌─────────────────────────────────────────┐                │
│  │  APISIX (PEP) ──→ Scorpio (NGSI-LD)     │                │
│  │  OPA (PDP)                              │                │
│  │  ODRL PAP + VCVerifier + TIL + CCS     │                │
│  │  provider.127.0.1.1.nip.io             │                │
│  └─────────────────────────────────────────┘                │
└─────────────────────────────────────────────────────────────┘
```

## Prerequisites

- Ubuntu 22.04+ (WSL2 or VM). See `00-windows-to-ubuntu.md` for Windows setup.
- 8 GB RAM, 4 CPU cores, 30 GB disk
- Internet access (for Helm chart downloads on first run)

---

## Deployment Order (run scripts in this order)

```bash
# Make all scripts executable
chmod +x *.sh

# Step 1: Install k3s, Helm, nginx ingress (run once)
bash 01-prerequisites.sh

# Step 2: Generate EC P-256 keys + DID:key for consumer and provider
bash 02-generate-identities.sh

# Step 3: Deploy Trust Anchor (TIL global registry)
bash 03-deploy-trust-anchor.sh

# Step 4: Deploy Consumer (Keycloak + VCVerifier)
bash 04-deploy-consumer.sh

# Step 5: Deploy Provider (APISIX + Scorpio + OPA + ODRL PAP)
bash 05-deploy-provider.sh

# Step 6: Register Consumer and Provider DIDs in Trust Anchor TIL
bash 06-register-participants.sh

# Step 7: Configure Provider's CCS with accepted credential types
bash 07-configure-provider-ccs.sh

# Step 8: Create ODRL access policy on Provider
bash 08-create-odrl-policy.sh

# Step 9: Full end-to-end test (401 → 403 → 200)
bash 09-test.sh
```

Total deployment time: ~30–40 minutes (mostly waiting for containers to pull and start).

---

## Files

| File | Purpose |
|---|---|
| `00-windows-to-ubuntu.md` | How to set up Ubuntu on Windows (WSL2) |
| `01-prerequisites.sh` | Install k3s, Helm, nginx ingress |
| `02-generate-identities.sh` | Generate EC keys + DIDs for consumer/provider |
| `did_helper.py` | Python script to derive did:key from PKCS12 |
| `03-deploy-trust-anchor.sh` | Deploy global Trust Anchor (TIL) |
| `04-deploy-consumer.sh` | Deploy Consumer with Keycloak |
| `05-deploy-provider.sh` | Deploy Provider with Scorpio + APISIX |
| `06-register-participants.sh` | Register DIDs in TIL |
| `07-configure-provider-ccs.sh` | Configure Provider's CCS |
| `08-create-odrl-policy.sh` | Create ODRL access control policy |
| `09-test.sh` | Full end-to-end test |
| `values/trust-anchor.yaml` | Helm values for Trust Anchor |
| `values/consumer.yaml` | Helm values for Consumer |
| `values/provider.yaml` | Helm values for Provider |
| `realm/fiware-realm.json` | Keycloak realm (OID4VC, roles, test users) |
| `keys/` | Generated keys and DIDs (created by script 02) |

---

## Hostnames

All services use `nip.io` wildcard DNS that resolves to `127.0.1.1` (Ubuntu's
default loopback alias — different from `127.0.0.1`).

| Service | URL |
|---|---|
| Trust Anchor TIL | http://til.127.0.1.1.nip.io |
| Trust Anchor CCS | http://ccs.127.0.1.1.nip.io |
| Consumer Keycloak | http://keycloak-consumer.127.0.1.1.nip.io |
| Consumer VCVerifier | http://verifier-consumer.127.0.1.1.nip.io |
| Provider Data Endpoint | http://provider.127.0.1.1.nip.io/ngsi-ld/v1/entities |
| Provider VCVerifier | http://verifier-provider.127.0.1.1.nip.io |
| Provider ODRL PAP | http://pap-provider.127.0.1.1.nip.io |

---

## Helm Charts

| Component | Chart | Version |
|---|---|---|
| Trust Anchor | dsc/data-space-connector | 0.2.0 |
| Consumer | dsc/data-space-connector | 7.17.0 |
| Provider | dsc/data-space-connector | 7.17.0 |

Chart repo: `https://fiware.github.io/data-space-connector/`

---

## Access Flow (how authentication works)

```
User → Keycloak (OID4VC)
     → Gets VerifiableCredential (JWT, type: OperatorCredential, role: READER)
     → Presents VC to Provider's VCVerifier
     → Gets VP access token
     → Calls Provider endpoint with Bearer token
     → APISIX validates token with VCVerifier JWKS
     → OPA checks ODRL policy (PAP)
     → If policy allows → request forwarded to Scorpio
     → 200 OK with NGSI-LD data
```

---

## Troubleshooting

**Pods stuck in Pending:**
```bash
kubectl describe pod <pod-name> -n <namespace>
# Usually a storage class issue. Verify: kubectl get sc
```

**nip.io not resolving:**
```bash
# Add Google DNS to WSL2:
echo "nameserver 8.8.8.8" | sudo tee /etc/resolv.conf
```

**Keycloak OID4VC endpoint not found:**
```bash
# Verify the KC_FEATURES env var is set:
kubectl exec -n consumer deploy/consumer-keycloak -- env | grep KC_FEATURES
# Should show: KC_FEATURES=oid4vc-vci
```

**Helm values key names wrong:**
```bash
# Check the actual chart values:
helm show values dsc/data-space-connector --version 7.17.0 | less
```

**APISIX not enforcing authentication:**
```bash
# Check APISIX routes are configured:
kubectl exec -n provider deploy/provider-apisix -- curl localhost:9180/apisix/admin/routes -H 'X-API-KEY: edd1c9f034335f136f87ad84b625c8f1'
```

**Full pod status check:**
```bash
kubectl get pods -A
kubectl get pods -n trust-anchor
kubectl get pods -n consumer
kubectl get pods -n provider
```
