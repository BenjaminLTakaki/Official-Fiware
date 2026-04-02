# Running Ubuntu on Windows (WSL2)

## Option A — WSL2 (Recommended, simplest)

WSL2 gives you a real Linux kernel inside Windows with near-native performance.
No VM manager, no separate installer.

### Step 1: Enable WSL2

Open **PowerShell as Administrator** and run:

```powershell
wsl --install
```

This installs WSL2 + Ubuntu automatically. Reboot when prompted.

If you already have WSL1, upgrade:
```powershell
wsl --set-default-version 2
wsl --install -d Ubuntu
```

### Step 2: Launch Ubuntu

- From Start Menu search "Ubuntu"  
- Or run `wsl` in any terminal

First launch asks you to create a username + password.

### Step 3: Update packages

```bash
sudo apt update && sudo apt upgrade -y
```

### Step 4: Copy deployment files into WSL

From inside Ubuntu (WSL), your Windows drive is mounted at `/mnt/c`, `/mnt/d`, etc.

```bash
# If your deploy folder is at G:\Official Fiware\deploy\
cp -r /mnt/g/"Official Fiware"/deploy ~/fiware-deploy
cd ~/fiware-deploy
```

### Step 5: Proceed to 01-prerequisites.sh

```bash
bash 01-prerequisites.sh
```

---

## Option B — VirtualBox (Isolated VM)

Use this if you want a fully isolated environment.

1. Download VirtualBox: https://www.virtualbox.org/wiki/Downloads
2. Download Ubuntu 22.04 LTS ISO: https://ubuntu.com/download/server
3. Create VM: 4 CPU, 8 GB RAM, 50 GB disk
4. Install Ubuntu, then SSH in or use the terminal

---

## Resource Requirements

| Component | Minimum | Recommended |
|---|---|---|
| RAM | 6 GB | 8 GB |
| CPU cores | 2 | 4 |
| Disk | 20 GB | 40 GB |

WSL2 uses up to half your system RAM by default. To adjust, create `C:\Users\<you>\.wslconfig`:

```ini
[wsl2]
memory=8GB
processors=4
```

Then restart: `wsl --shutdown` in PowerShell.

---

## Troubleshooting

**"WSL 2 requires an update to its kernel component"**  
Download and install: https://aka.ms/wsl2kernel

**k3s won't start in WSL2**  
Some WSL2 kernels are missing cgroup v2 support. Run:
```bash
cat /proc/version
```
If kernel < 5.15, update WSL: `wsl --update` in PowerShell.

**nip.io doesn't resolve**  
WSL2 uses Windows DNS by default. Add Google DNS:
```bash
echo "nameserver 8.8.8.8" | sudo tee /etc/resolv.conf
```
