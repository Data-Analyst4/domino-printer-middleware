# Domino Printer Middleware — Command Manual

Base URL (local): `http://127.0.0.1:5003`  
Public (typical): `https://domino-print.k95foods.com`

If `API_KEY` is set in `site.env`, send header `X-API-Key: <key>` on all routes except `/`, `/health`, and `/version`.

---

## 1. HTTP API endpoints

| Method | Path | Use |
|--------|------|-----|
| `GET` | `/` | Service info and list of available routes |
| `GET` | `/health` | Liveness check (installers / tunnel / ERP) |
| `GET` | `/version` | App version info |
| `GET` | `/printers` | List configured printers + connection state |
| `POST` | `/test/ping` | ICMP ping to printer IP |
| `POST` | `/test/port` | Check TCP port open (default **7000**) |
| `POST` | `/test/connection` | Ping + TCP port + Codenet `identify` in one call |
| `POST` | `/print` | Run a Domino action / print job |
| `GET` | `/job/<job_id>` | Look up one past job by id |
| `GET` | `/jobs` | List recent jobs (newest first) |

### Examples

```powershell
curl http://127.0.0.1:5003/health
curl http://127.0.0.1:5003/version
curl http://127.0.0.1:5003/printers

curl -X POST http://127.0.0.1:5003/test/ping -H "Content-Type: application/json" -d "{\"ip\":\"192.168.1.50\"}"
curl -X POST http://127.0.0.1:5003/test/port -H "Content-Type: application/json" -d "{\"ip\":\"192.168.1.50\",\"port\":7000}"
curl -X POST http://127.0.0.1:5003/test/connection -H "Content-Type: application/json" -d "{\"ip\":\"192.168.1.50\",\"port\":7000}"
```

With configured `printer_id`:

```json
{ "printer_id": "DOMINO_AX_1" }
```

---

## 2. Print actions (`POST /print`)

Every print call needs at least:

```json
{
  "printer_id": "DOMINO_AX_1",
  "action": "<action_name>"
}
```

Optional override:

```json
"printer": { "ip": "192.168.1.50", "port": 7000 }
```

### High-level actions (recommended for ERP)

Photocell / factory job path (**does not send Print Go `N`**):

| Action | Required fields | Codenet |
|--------|-----------------|---------|
| `put_named_label_online` | `label_name` | Named label online (`ON`) |
| `query_online_label` | — | Query online label (`P1?`). Echo may be truncated (e.g. `NOI`) |
| `push_fifo_fields` | `fields[]` or `csv` | FIFO data (`OE`). Alias: `send_fifo_data` + `data` |
| `soft_stop` | — | Head disable (`Q1N`) — pause prints |
| `soft_resume` | — | Head enable (`Q1Y`) — allow prints again |
| `sequence_on` | — | Jet **Sequence ON** / UI Start (`OS 1`) — Ready to print |
| `sequence_off` | — | Jet **Sequence OFF** (`OS 0`) — Standby (admin / end-of-job) |
| `query_sequence` | — | Query sequence state (`OS ?`) |
| `get_print_count` | — | Read **T1** (photocell) + **T2** (prints since power-on) |
| `query_product_count` | optional `counter_id` 1\|2 | Single counter query (`T1?` / `T2?`) |
| `identify` | — | Printer identity (`A?`) |
| `get_status` | — | Extended status (`O1?`) |

Legacy slot print (**does send `N`** — not the factory photocell path):

| Action | Required fields | Use |
|--------|-----------------|-----|
| `print_stored_label` | `label_slot` (or `default_label_slot` in config) | Select stored label (`P`) then trigger print (`N`) |
| `print_product` | `product_code` | Map ERP product → label slot via `label_map`, then print |

**Put named label online**

```json
{
  "printer_id": "DOMINO_AX_1",
  "printer": { "ip": "192.168.1.40", "port": 7000 },
  "action": "put_named_label_online",
  "label_name": "NOICE KM 200ML"
}
```

**Push FIFO fields (one bottle; photocell prints)**

```json
{
  "printer_id": "DOMINO_AX_1",
  "action": "push_fifo_fields",
  "fields": ["95.00", "KFBNIKHIL7", "11/08/2026", "10/05/2027"],
  "csv": "95.00,KFBNIKHIL7,11/08/2026,10/05/2027"
}
```

**Soft stop / resume**

```json
{ "printer_id": "DOMINO_AX_1", "action": "soft_stop" }
```

```json
{ "printer_id": "DOMINO_AX_1", "action": "soft_resume" }
```

**Print stored label**

```json
{
  "printer_id": "DOMINO_AX_1",
  "action": "print_stored_label",
  "label_slot": "001",
  "product_detect": "1"
}
```

**Print by product code**

```json
{
  "printer_id": "DOMINO_AX_1",
  "action": "print_product",
  "product_code": "SKU001"
}
```

(`label_map` in `config/printers.json` must map `SKU001` → e.g. `"001"`.)

### Low-level / admin Codenet actions

| Action | Required fields | Use |
|--------|-----------------|-----|
| `identify` | — | Confirm printer identity (Codenet `A?`) |
| `get_codenet_version` | — | Read Codenet protocol version (`}D?`) |
| `get_status` | — | Extended status (`O1?`) — alias of `get_extended_status` |
| `get_basic_status` | — | Basic status (`1C?`) |
| `get_extended_status` | — | Extended status + LED state (`O1?`) |
| `put_label_online` | `label_slot` | Put stored label slot online (`P`) without printing |
| `put_named_label_online` | `label_name` | Put named label online (`ON`) without printing |
| `query_online_label` | — | Query which label is online (`P1?`) |
| `print_go` | optional `product_detect` (default `1`) | Trigger print like product detect (`N`) — **not** ERP job path |
| `store_label` | `label_slot`, `label_data` | Store label data in printer (`S`) |
| `download_label_without_save` | `slot`, `label_data` | Download label to buffer without saving (`OQ`) |
| `send_fifo_data` | `data` | Send ASCII FIFO data (`OE`). Alias of `push_fifo_fields` |
| `push_fifo_fields` | `fields[]` or `csv` | Same `OE` as `send_fifo_data`; `fields` joined in POD order |
| `soft_stop` | — | Pause prints (`Q1N`) — no `N` |
| `soft_resume` | — | Resume prints (`Q1Y`) — no `N` |

**Identify**

```json
{ "printer_id": "DOMINO_AX_1", "action": "identify" }
```

**Status**

```json
{ "printer_id": "DOMINO_AX_1", "action": "get_status" }
```

**Put label online only**

```json
{
  "printer_id": "DOMINO_AX_1",
  "action": "put_label_online",
  "label_slot": "001"
}
```

**Trigger print only**

```json
{
  "printer_id": "DOMINO_AX_1",
  "action": "print_go",
  "product_detect": "1"
}
```

**Store label**

```json
{
  "printer_id": "DOMINO_AX_1",
  "action": "store_label",
  "label_slot": "009",
  "label_data": "<ascii label data>"
}
```

**Download without save**

```json
{
  "printer_id": "DOMINO_AX_1",
  "action": "download_label_without_save",
  "slot": "001",
  "label_data": "<ascii label data>"
}
```

**FIFO / variable data**

```json
{
  "printer_id": "DOMINO_AX_1",
  "action": "send_fifo_data",
  "data": "BATCH123"
}
```

### curl example

```powershell
curl -X POST http://127.0.0.1:5003/print -H "Content-Type: application/json" -d "{\"printer_id\":\"DOMINO_AX_1\",\"action\":\"print_stored_label\",\"label_slot\":\"001\"}"
```

### Job lookup

```powershell
curl http://127.0.0.1:5003/jobs
curl http://127.0.0.1:5003/job/<job_id>
```

---

## 3. Install & service commands

### Windows

| Command | Use |
|---------|-----|
| `install.bat` | One-click install (Python, venv, NSSM service, optional Cloudflare) |
| `install.bat -SkipCloudflare` | Install middleware only (LAN, no public URL) |
| `uninstall.bat` | Remove Windows services (files stay on disk) |
| `sc stop DominoPrinterMiddleware` | Stop middleware service |
| `sc start DominoPrinterMiddleware` | Start middleware service |
| `start.bat` | Manual/dev start of the app |
| `start-demo-printer.bat` | Start local mock Domino printer on TCP 7000 |

### Linux

| Command | Use |
|---------|-----|
| `./install-linux.sh` | One-click install + systemd service |
| `./install-linux.sh --skip-cloudflare` | Install without cloudflared |
| `./install-linux.sh --no-start` | Install unit but do not start yet |
| `./uninstall-linux.sh` | Remove systemd service |
| `sudo systemctl status domino-printer-middleware` | Service status |
| `sudo systemctl restart domino-printer-middleware` | Restart service |
| `sudo journalctl -u domino-printer-middleware -f` | Follow logs |

### Dev / manual run

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
copy config\printers.json.example config\printers.json
python main.py
```

### Demo printer (no hardware)

```powershell
.\start-demo-printer.bat
# or
python scripts\mock_domino_printer.py --host 127.0.0.1 --port 7000

copy config\printers.demo.json config\printers.json
python main.py
```

---

## 4. Quick “which command do I use?”

| Goal | Use |
|------|-----|
| Is middleware up? | `GET /health` |
| Is printer on the network? | `POST /test/ping` |
| Is Codenet TCP port open? | `POST /test/port` |
| Full readiness (ping + port + identify) | `POST /test/connection` |
| Print a stored label | `POST /print` → `print_stored_label` |
| Print from ERP product code | `POST /print` → `print_product` |
| Check printer identity / status | `POST /print` → `identify` / `get_status` |
| See what was sent earlier | `GET /jobs` or `GET /job/<id>` |
| Install on site PC | `install.bat` / `./install-linux.sh` |

---

## 5. Codenet PDF commands useful like Rynan (`STAR` / `DATA`)

Source: `docs/Ax Series Codenet Protocol.pdf` (EPT033760 Issue 2).  
Rynan today: `STAR` (pick template) → `DATA` (POD1/POD2…) → print.  
Domino does **not** use JSON `STAR`/`DATA`; same jobs map to Codenet bytes below.

### Rynan → Domino mapping

| Rynan idea | Domino Codenet | Hex ID | Middleware action today | Priority |
|------------|----------------|--------|-------------------------|----------|
| Pick template (`STAR`) | Get label from store & put online | `P` `50h` | `print_stored_label` / `put_label_online` | **Core** |
| Pick template by name | Retrieve named label & put online | `ON` `4F4Eh` | `put_named_label_online` | **Core** |
| Send POD / variable fields (`DATA`) | Send data to FIFO (updatable text) | `OE` `4F45h` | `push_fifo_fields` / `send_fifo_data` | **Core** |
| Trigger print / photocell | Print Go | `N` `4Eh` | `print_go` (legacy slot path only — **not** ERP job path) | Legacy |
| Connection / handshake | Printer Identity | `A` `41h` | `identify` | **Core** |
| Health / ready? | Extended current status | `O1` `4F31h` | `get_status` | **Core** |
| Upload / change template | Store label (3-digit slot) | `S` `53h` | `store_label` | Useful |
| Store by product name | Store label variable-length name | `OM` `4F4Dh` | *not built yet* | Useful |
| One-shot dynamic label | Download label without save | `OQ` `4F51h` | `download_label_without_save` | Useful |
| Clear pending variable data | Reset FIFO buffer | `}J` `7D4Ah` | *not built yet* | Useful |
| Ink / makeup check | Read liquid levels | `y` `79h` | *not built yet* | Dashboard |
| Start/stop jet (admin) | Sequence ink jet on/off | `OS` `4F53h` | *not built yet* | Admin only |
| Sync date/time | Set real-time clock | `C` `43h` | *not built yet* | Useful |
| Protocol check | Get Codenet version | `}D` `7D44h` | `get_codenet_version` | Diagnostics |
| FIFO setup (once) | Configure FIFO for external data | `OP` `4F50h` | *not built yet* | Setup / admin |
| Enable printing | Head Enable | `Q` `51h` | `soft_stop` (`Q1N`) / `soft_resume` (`Q1Y`) | **Core** |
| Wipe store | Clear All Labels | `R` `52h` | *not built yet* | Admin |
| Counts | Product Counts | `T` `54h` | *not built yet* | Dashboard |
| Basic status history | Status Request | `1` `31h` | `get_basic_status` | Diagnostics |

### Closest ERP flow (like Rynan)

**A — Stored label only (no POD fields)** — same role as `STAR` then print:

```text
P (select slot) → N (print go)
```

Middleware: `action: print_stored_label` + `label_slot`.

**B — Template + variable data (ERP photocell path):**

```text
ON (named label) → OE (FIFO / POD fields) → photocell prints
  pause: Q1N    resume: Q1Y
  do not send N; do not send }J / }D on this firmware
```

Middleware actions: `put_named_label_online` → `push_fifo_fields` → `soft_stop` / `soft_resume`.

**C — Product-name templates (closest to Rynan `templatename`)**

```text
ON (label_name=NOICE KM 200ML) → OE (fields in POD order) → photocell
```

### PDF notes that matter for ERP

- Frame: `ESC` (`1B`) + command + params + `EOT` (`04`). ACK=`06`, NAK=`15` + 3-digit code.
- Use printer setting **On Processed** so ACK means accepted, not only received.
- Official `P` format includes head select: `ESC P 1 <slot 001–255> EOT` (e.g. slot 009 → `1B503130303904`). Our builder currently sends `ESC P <slot>` without the `1` head byte — verify on real hardware if ACK fails.
- `OE` length is ASCII `0001`–`1024`; label must already contain updatable text fields (Domino’s POD equivalent).
- Unicode variable data uses Ethernet data port **16000**, not Codenet `OE`.
- ERP photocell path uses **`sequence_on` (`OS 1`)** at demo start (UI Start). Prefer that over raw hex.
- Do **not** expose clear-all (`R`) or raw hex to normal ERP operators. Use `sequence_off` only when intentionally stopping the jet.

### Recommended build order (match Rynan usefulness)

1. Keep **`P` + `N`** (already in `print_stored_label`).
2. Add combined **`print_with_data`**: `P`/`ON` → `OE` → `N` (Rynan `STAR`+`DATA`).
3. Add **`ON` / `OM`** for named templates by product code.
4. Add **`}J`** (reset FIFO), **`y`** (liquids), **`OS`** (admin jet), **`C`** (clock).
5. Only then invest in **`OQ`** dynamic full-label download (needs Domino format codes inside `label_data`).

---

## Related docs

- [README.md](../README.md) — overview & quick start  
- [ERP_INTEGRATION.md](../ERP_INTEGRATION.md) — ERP payload / routing  
- [PRINTER_SETUP_AND_TEST.md](../PRINTER_SETUP_AND_TEST.md) — TouchPanel + tests  
- [DOMINO_AX_FUNCTIONALITY_AND_WEB_APP_GUIDE.md](DOMINO_AX_FUNCTIONALITY_AND_WEB_APP_GUIDE.md) — Codenet protocol detail  
- [Ax Series Codenet Protocol.pdf](Ax%20Series%20Codenet%20Protocol.pdf) — full command reference  
