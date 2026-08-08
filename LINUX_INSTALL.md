# Domino Printer Middleware — Linux (Ubuntu) install

One-click install for **Ubuntu/Debian**. Sets up a systemd service that starts on boot and restarts on crash.

| App | Folder | Port | systemd service |
|-----|--------|------|-----------------|
| Domino | repo root | **5003** | `domino-printer-middleware` |

## Install (one command)

```bash
cd /path/to/domino-printer-middleware
chmod +x install-linux.sh uninstall-linux.sh
./install-linux.sh
```

You will be prompted for `sudo`. The script installs Python packages, creates a virtualenv, copies config examples if missing, and starts the service.

### Options

```bash
./install-linux.sh --skip-cloudflare   # skip cloudflared download
./install-linux.sh --no-start          # install unit but do not start yet
```

### After install

1. Edit printer IP: `config/printers.json`
2. Check health:
   ```bash
   curl http://127.0.0.1:5003/health
   ```
3. Useful commands:
   ```bash
   sudo systemctl status domino-printer-middleware
   sudo journalctl -u domino-printer-middleware -f
   sudo systemctl restart domino-printer-middleware
   ```

### Uninstall service

```bash
./uninstall-linux.sh
```

App files and `.venv` stay on disk; delete the repo folder if you want a full wipe.

### Optional Cloudflare tunnel

`install-linux.sh` installs `cloudflared` when possible. To expose a public HTTPS URL:

```bash
cloudflared tunnel login
cloudflared tunnel create domino-print
cloudflared tunnel route dns domino-print your-hostname.example.com
# edit ~/.cloudflared/config.yml then:
sudo cloudflared service install
```
