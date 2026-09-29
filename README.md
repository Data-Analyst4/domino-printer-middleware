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

## Camera import (optional, same as Rynan)

Only for `send_fifo_data` / `push_fifo_fields`. Omit `camera_import` for plain FIFO (no camera call).

```json
{
  "printer_id": "DOMINO_AX_1",
  "action": "send_fifo_data",
  "data": "95.00,BATCH,11/08/2026,10/05/2027",
  "camera_import": {
    "enabled": true,
    "barcode": "8906164010577",
    "url": "http://192.168.0.68:5001/api/import_batch"
  }
}
```

- POSTs `{ "barcode", "text" }` to the camera URL **before** Domino `OE` (`text` = FIFO CSV).
- Print `success` is Domino-only; check `camera_import.erp_alert_recommended` for WhatsApp.
- Env defaults: `CAMERA_IMPORT_ENABLED`, `CAMERA_IMPORT_BATCH_URL`, `CAMERA_IMPORT_TIMEOUT` (see `config/site.env.example`).

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
