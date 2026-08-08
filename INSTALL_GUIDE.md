# Domino Printer Middleware — One-Click Install (Site PC)

Windows installer for this repo only. Does **not** install or stop Rynan `printer-middleware`.

| | Domino |
|--|--------|
| Folder | `C:\domino-printer-middleware` (or any path to this repo) |
| Installer | **`install.bat`** |
| Service | **`DominoPrinterMiddleware`** |
| Port | **`5003`** |
| Public URL (optional) | `domino-print.k95foods.com` |

---

## 1. What `install.bat` does

1. Self-elevate to Administrator  
2. Install Python 3.11 via winget if missing  
3. Create `.venv` + `pip install -r requirements.txt`  
4. Create `config\printers.json` / `site.env` from examples if missing  
5. Download NSSM if needed  
6. Install **DominoPrinterMiddleware** Windows service (boot start + crash restart)  
7. Verify `http://127.0.0.1:5003/health`  

Optional: `install.bat -WithCloudflare` for a separate public hostname.

---

## 2. Get the app onto the PC

1. Clone or copy this repo to `C:\domino-printer-middleware`
2. Open that folder

```cmd
cd /d C:\domino-printer-middleware
```

---

## 3. Configure Domino IP

```cmd
cd /d C:\domino-printer-middleware
copy config\printers.json.example config\printers.json
notepad config\printers.json
```

Set real Domino LAN IP and port **7000**:

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

On the Domino TouchPanel: **Codenet + TCP + port 7000 + Enabled**, then restart printer.

---

## 4. One-click install

**Right-click** `install.bat` → **Run as administrator**

Or:

```cmd
cd /d C:\domino-printer-middleware
install.bat
```

Health: `http://127.0.0.1:5003/health`

---

## 5. Uninstall

**Right-click** `uninstall.bat` → **Run as administrator**

---

## 6. Linux

See [LINUX_INSTALL.md](LINUX_INSTALL.md).
