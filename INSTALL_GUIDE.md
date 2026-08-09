# Domino Printer Middleware — One-Click Install (Site PC)

**Right-click** [`install.bat`](install.bat) → **Run as administrator**  
(or double-click — it self-elevates).

That is the full install. No other steps required for the Windows services.

| | After install |
|--|--|
| Folder | wherever this repo lives (e.g. `C:\domino-printer-middleware`) |
| Service | **`DominoPrinterMiddleware`** — start on boot, restart on crash |
| Port | **`5003`** |
| Cloudflare | **`DominoCloudflared`** — start on boot (default) |
| Public URL | **`https://domino-print.k95foods.com`** |

LAN-only (no public URL):

```cmd
install.bat -SkipCloudflare
```

---

## What one-click does

1. Self-elevate to Administrator  
2. Install Python 3.11 via winget if missing  
3. Create `.venv` + `pip install -r requirements.txt`  
4. Create `config\printers.json` / `site.env` from examples if missing  
5. Download NSSM if needed  
6. Install **`DominoPrinterMiddleware`** (boot + crash restart) and start it  
7. Install / create Cloudflare tunnel + DNS when `cloudflared` login exists  
8. Install **`DominoCloudflared`** (boot + crash restart)  
9. Verify `http://127.0.0.1:5003/health` (and public `/health` when possible)

---

## Get the app onto the PC

**Option A — Git**

```cmd
cd /d C:\
git clone https://github.com/Data-Analyst4/domino-printer-middleware.git
cd domino-printer-middleware
install.bat
```

**Option B — ZIP**

1. Download: https://github.com/Data-Analyst4/domino-printer-middleware/archive/refs/heads/master.zip  
2. Extract to `C:\domino-printer-middleware`  
3. Double-click **`install.bat`**

---

## After install — set Domino printer IP

Edit `config\printers.json`:

```json
{
  "DOMINO_AX_1": {
    "ip": "192.168.1.50",
    "port": 7000,
    "protocol": "domino_ax_codenet",
    "default_label_slot": "001",
    "enabled": true
  }
}
```

On the Domino TouchPanel: **Codenet + TCP + port 7000 + Enabled**, then restart the printer.

```cmd
sc stop DominoPrinterMiddleware
sc start DominoPrinterMiddleware
```

---

## Cloudflare note

If this PC was never logged into Cloudflare Zero Trust, run once:

```cmd
cloudflared tunnel login
```

Then run **`install.bat`** again — it creates the `domino-print` tunnel, DNS, and Windows service automatically.

---

## Uninstall

**Right-click** [`uninstall.bat`](uninstall.bat) → **Run as administrator**

Removes `DominoPrinterMiddleware` and `DominoCloudflared`. App files stay on disk.

---

## Linux

See [LINUX_INSTALL.md](LINUX_INSTALL.md) — `./install-linux.sh` is the one-click Ubuntu/Debian path (systemd auto-start + restart).
