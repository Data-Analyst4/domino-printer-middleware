# Domino Printer Middleware

HTTP middleware for **Domino Ax-Series** printers (Codenet 2 over TCP).  
Independent from the Rynan `printer-middleware` — use a separate URL/port for Domino.

| | This app |
|--|--|
| Default port | **5003** |
| Suggested public URL | `https://domino-print.k95foods.com` |
| Printer protocol | Codenet bytes over TCP **7000** |

## Quick start (Windows site PC) — one click

1. Clone or unzip this repo  
2. **Double-click** [`install.bat`](install.bat) (accepts UAC)

That installs Python if needed, `.venv`, Windows service **`DominoPrinterMiddleware`** (boot + crash restart), and **Cloudflare** tunnel service **`DominoCloudflared`** when possible → **`https://domino-print.k95foods.com`**.

LAN only: `install.bat -SkipCloudflare`

Full steps: [INSTALL_GUIDE.md](INSTALL_GUIDE.md) · Linux: [LINUX_INSTALL.md](LINUX_INSTALL.md)

### Manual start (dev)

```powershell
cd domino-printer-middleware
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
copy config\printers.json.example config\printers.json
# edit config\printers.json with real Domino IP
python main.py
```

Health check: `http://127.0.0.1:5003/health`

## Configure Domino printer (TouchPanel)

Full checklist + ping/port/print tests: **[PRINTER_SETUP_AND_TEST.md](PRINTER_SETUP_AND_TEST.md)**

Living study notes from Domino Product + Codenet PDFs, plus all live test results: **[docs/DOMINO_STUDY_AND_TEST_LOG.md](docs/DOMINO_STUDY_AND_TEST_LOG.md)** (updated after each test)

1. `Home > Setup > Printer network > Advanced`
2. Protocol Setting → **Codenet**
3. Protocol Mode → **TCP**
4. Protocol Enabled → **On**
5. TCP Port → **7000**
6. Response timing → **On Processed**
7. Restart printer
8. Store labels in printer (slots like `001`, `002`)

Quick connection test:

```powershell
curl -X POST http://127.0.0.1:5003/test/connection -H "Content-Type: application/json" -d "{\"ip\":\"192.168.1.50\",\"port\":7000}"
```

## Example print request

```json
POST /print
{
  "printer_id": "DOMINO_AX_1",
  "action": "print_stored_label",
  "label_slot": "001",
  "product_detect": "1"
}
```

Or map ERP product codes via `label_map` in `config/printers.json`:

```json
{
  "printer_id": "DOMINO_AX_1",
  "action": "print_product",
  "product_code": "SKU001"
}
```

## ERP changes

See **[ERP_INTEGRATION.md](ERP_INTEGRATION.md)** for ERP printer configuration and API calls.

## Protocol docs

- [docs/DOMINO_AX_CODENET_INTEGRATION.md](docs/DOMINO_AX_CODENET_INTEGRATION.md)
- [docs/DOMINO_AX_FUNCTIONALITY_AND_WEB_APP_GUIDE.md](docs/DOMINO_AX_FUNCTIONALITY_AND_WEB_APP_GUIDE.md)
- PDFs under `docs/`

## Demo printer (no hardware)

Mimics a successful Domino Ax Codenet printer on TCP **7000** (identify, status, store, print → ACK).

```powershell
# Terminal 1 — demo printer
.\start-demo-printer.bat
# or: python scripts\mock_domino_printer.py --host 127.0.0.1 --port 7000

# Point middleware at the demo
copy config\printers.demo.json config\printers.json

# Terminal 2 — middleware
python main.py
```

Then:

```powershell
curl -X POST http://127.0.0.1:5003/test/connection -H "Content-Type: application/json" -d "{\"ip\":\"127.0.0.1\",\"port\":7000}"
curl -X POST http://127.0.0.1:5003/print -H "Content-Type: application/json" -d "{\"printer_id\":\"DOMINO_AX_DEMO\",\"action\":\"print_stored_label\",\"label_slot\":\"001\"}"
```
