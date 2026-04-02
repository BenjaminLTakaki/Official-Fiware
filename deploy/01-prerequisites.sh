#!/usr/bin/env bash
# =============================================================================
# 01-prerequisites.sh
# Install k3s, Helm, and kubectl on Ubuntu. Add the FIWARE Helm repo.
# Run this ONCE on a fresh Ubuntu system (WSL2 or VM).
# =============================================================================
set -euo pipefail

echo "========================================"
echo " FIWARE DSC — Prerequisites installer"
echo "========================================"

# --- Install system dependencies ---
echo "[1/5] Updating apt and installing dependencies..."
sudo apt-get update -y
sudo apt-get install -y curl wget git openssl python3 python3-pip jq

# Install Python cryptography library (needed by did_helper.py)
pip3 install cryptography --quiet

# --- Install k3s (lightweight Kubernetes) ---
echo "[2/5] Installing k3s..."
if ! command -v k3s &>/dev/null; then
  curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="--disable=traefik" sh -
  # Note: we disable the default Traefik and use nginx-ingress instead
  # (nginx handles the nip.io routing more predictably)
fi

# Wait for k3s to be ready
echo "    Waiting for k3s node to become Ready..."
sudo k3s kubectl wait --for=condition=ready node --all --timeout=120s

# Set up kubectl config for the current user
mkdir -p ~/.kube
sudo cp /etc/rancher/k3s/k3s.yaml ~/.kube/config
sudo chown "$(id -u):$(id -g)" ~/.kube/config
chmod 600 ~/.kube/config
export KUBECONFIG=~/.kube/config
echo "export KUBECONFIG=~/.kube/config" >> ~/.bashrc

# --- Install nginx ingress controller ---
echo "[3/5] Installing nginx ingress controller..."
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.8.2/deploy/static/provider/cloud/deploy.yaml

echo "    Waiting for ingress-nginx to be ready (up to 3 min)..."
kubectl wait --namespace ingress-nginx \
  --for=condition=ready pod \
  --selector=app.kubernetes.io/component=controller \
  --timeout=180s

# Patch nginx to listen on 127.0.1.1 (Ubuntu loopback alias used by nip.io)
echo "    Configuring nginx to bind to 127.0.1.1..."
kubectl patch svc ingress-nginx-controller -n ingress-nginx \
  -p '{"spec":{"externalIPs":["127.0.1.1"]}}'

# Verify the loopback alias exists; add it if missing
if ! ip addr show lo | grep -q "127.0.1.1"; then
  echo "    Adding 127.0.1.1 loopback alias..."
  sudo ip addr add 127.0.1.1/8 dev lo || true
  # Make it persistent across reboots
  echo "post-up ip addr add 127.0.1.1/8 dev lo" | sudo tee -a /etc/network/interfaces.d/loopback-alias || true
fi

# --- Install Helm ---
echo "[4/5] Installing Helm..."
if ! command -v helm &>/dev/null; then
  curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
fi

# --- Add Helm repositories ---
echo "[5/5] Adding Helm repositories..."
helm repo add dsc https://fiware.github.io/data-space-connector/
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update

echo ""
echo "========================================"
echo " All prerequisites installed!"
echo ""
echo " Verify with:"
echo "   kubectl get nodes"
echo "   helm version"
echo "   helm search repo dsc"
echo "========================================"
