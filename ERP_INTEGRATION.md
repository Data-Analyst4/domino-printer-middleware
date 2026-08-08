# ERP Changes For Domino Middleware

Use this when attaching a **Domino** printer in ERP with a **different middleware URL** than the existing Rynan printer.

Existing Rynan middleware stays unchanged.

| Role | App | URL (example) |
|------|-----|----------------|
| Rynan CIJ / POD printers | Current printer-middleware | `https://r10-print.k95foods.com` |
| Domino Ax printers | This repo (`domino-printer-middleware`) | `https://domino-print.k95foods.com` |

Local ports if no tunnel yet:

| App | Port |
|-----|------|
| Rynan | `5001` / `5002` |
| Domino | **`5003`** |

---

## 1. Add a second printer middleware URL in ERP

Wherever ERP stores the Rynan print base URL today (site settings, env, printer master), add a **separate** Domino base URL field.

### Recommended ERP config shape

```json
{
  "printer_middlewares": {
    "rynans": {
      "base_url": "https://r10-print.k95foods.com",
      "protocol": "rynans_json_tcp"
    },
    "domino": {
      "base_url": "https://domino-print.k95foods.com",
      "protocol": "domino_ax_codenet"
    }
  }
}
```

If ERP only has one global URL today, do **not** overwrite it. Add something like:

- `PRINT_MIDDLEWARE_URL` → keep Rynan URL
- `DOMINO_PRINT_MIDDLEWARE_URL` → new Domino URL

Or per-printer:

| Field | Rynan printer | Domino printer |
|-------|---------------|----------------|
| `middleware_url` | `https://r10-print.k95foods.com` | `https://domino-print.k95foods.com` |
| `printer_type` / `protocol` | `rynans` / `json_tcp` | `domino` / `domino_ax_codenet` |
| `printer_id` | e.g. `P1` | e.g. `DOMINO_AX_1` |
| `ip` | printer LAN IP | Domino LAN IP |
| `port` | `2030` | **`7000`** |

---

## 2. Route print calls by printer type

ERP must choose middleware URL from the printer record, not a single hard-coded URL.

### Pseudocode

```javascript
async function sendPrint(printer, payload) {
  const baseUrl = printer.middleware_url; // different per printer type
  const res = await fetch(`${baseUrl}/print`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      // only if Domino middleware has API_KEY set:
      // "X-API-Key": process.env.DOMINO_PRINT_API_KEY
    },
    body: JSON.stringify(payload),
  });
  return res.json();
}
```

Rules:

1. Rynan printers → Rynan `middleware_url` + Rynan payload (`STAR` / `DATA`).
2. Domino printers → Domino `middleware_url` + Domino payload (`action` / `label_slot`).
3. Never send Rynan `STAR`/`DATA` JSON to the Domino middleware URL.
4. Never send Domino Codenet actions to the Rynan middleware URL.

---

## 3. Change the print request body for Domino

### Current Rynan request (keep for Rynan printers)

```json
{
  "printer_id": "P1",
  "printer": { "ip": "192.168.29.110", "port": 2030 },
  "command": {
    "command": "DATA",
    "data": { "POD1": "1122", "POD2": "2233" }
  }
}
```

### New Domino request (use for Domino printers)

**Option A — print by stored label slot (recommended first):**

```json
{
  "printer_id": "DOMINO_AX_1",
  "printer": { "ip": "192.168.1.50", "port": 7000 },
  "action": "print_stored_label",
  "label_slot": "001",
  "product_detect": "1"
}
```

**Option B — print by ERP product code (middleware maps to slot):**

Configure mapping in Domino middleware `domino/config/printers.json`:

```json
"label_map": { "SKU001": "001", "SKU002": "002" }
```

ERP sends:

```json
{
  "printer_id": "DOMINO_AX_1",
  "action": "print_product",
  "product_code": "SKU001"
}
```

**Option C — status / identify (admin tools):**

```json
{ "printer_id": "DOMINO_AX_1", "action": "identify" }
```

```json
{ "printer_id": "DOMINO_AX_1", "action": "get_status" }
```

---

## 4. ERP UI / printer master changes

On the **Add / Edit Printer** screen:

1. Add printer type: `Rynan` | `Domino`.
2. When type = Domino:
   - Default middleware URL → Domino URL (`https://domino-print.k95foods.com`)
   - Default TCP port → `7000`
   - Show fields: `label_slot` or product→slot mapping (not POD1/POD2 template fields)
3. When type = Rynan:
   - Keep current URL, port `2030`, template/POD fields

Suggested new fields on Domino printer records:

| ERP field | Purpose |
|-----------|---------|
| `middleware_url` | Domino middleware base URL |
| `printer_id` | Must match key in Domino `printers.json` |
| `ip` / `port` | Domino LAN address / `7000` |
| `default_label_slot` | Fallback slot if product has no mapping |
| `product_label_map` | Optional ERP-side map product → slot (or keep map only in middleware) |

---

## 5. Handle Domino response shape in ERP

Success example:

```json
{
  "success": true,
  "job_id": "...",
  "printer_id": "DOMINO_AX_1",
  "protocol": "domino_ax_codenet",
  "action": "print_stored_label",
  "label_slot": "001",
  "steps": [
    { "command": "put_label_online", "hex": "1B5030303104", "ok": true, "response": "06" },
    { "command": "print_go", "hex": "1B4E3104", "ok": true, "response": "06" }
  ]
}
```

Failure example:

```json
{
  "success": false,
  "error": "Command parameter out of permitted range (NAK 007)",
  "nak_code": "007",
  "steps": [ ... ]
}
```

ERP changes:

- Treat `success === true` as printed/accepted (same idea as Rynan `YES`).
- Show `error` / `nak_code` to operators (instead of Rynan `NYES` / `SYSN` codes).
- Optional: poll `GET {domino_base}/job/{job_id}` if you store `job_id`.

Do **not** expect Domino responses like `DATA;YES` or `{"status":"YES"}`.

---

## 6. Production print flow mapping

| ERP event | Rynan today | Domino |
|-----------|-------------|--------|
| Start job / select template | `STAR` + `templatename` | Ensure label exists on Domino; use `label_slot` or `print_product` |
| Send variable data | `DATA` + POD fields | Later: `send_fifo_data` / download label (phase 2) |
| Trigger print | Often part of DATA / photocell | `print_stored_label` → middleware sends `P` then `N` |
| Health check | `GET /health` on Rynan URL | `GET /health` on **Domino URL** |

**Phase 1 (ship this first):** ERP only calls `print_stored_label` or `print_product`. Labels are designed/stored on the Domino printer UI.

**Phase 2 (optional):** ERP sends batch/MRP/expiry via `send_fifo_data` or dynamic label download.

---

## 7. Cloudflare / public URL (ops)

Create a **second** tunnel hostname; do not reuse `r10-print.k95foods.com`.

Example:

```text
domino-print.k95foods.com  →  http://127.0.0.1:5003
```

ERP Domino printer `middleware_url` = `https://domino-print.k95foods.com`

---

## 8. ERP checklist

- [ ] Keep existing Rynan middleware URL unchanged
- [ ] Add Domino middleware URL (site setting or per-printer)
- [ ] Add printer type `Domino` on printer master
- [ ] Domino printers use port `7000` and Domino URL
- [ ] Build Domino payload with `action` (not `STAR`/`DATA`)
- [ ] Map product → `label_slot` (ERP or middleware `label_map`)
- [ ] Parse Domino `success` / `nak_code` for UI errors
- [ ] Point Domino health checks at Domino `/health`
- [ ] Test: `POST https://domino-print.k95foods.com/print` with `print_stored_label`

---

## 9. Curl smoke tests

```bash
curl https://domino-print.k95foods.com/health

curl -X POST https://domino-print.k95foods.com/print ^
  -H "Content-Type: application/json" ^
  -d "{\"printer_id\":\"DOMINO_AX_1\",\"action\":\"identify\"}"

curl -X POST https://domino-print.k95foods.com/print ^
  -H "Content-Type: application/json" ^
  -d "{\"printer_id\":\"DOMINO_AX_1\",\"action\":\"print_stored_label\",\"label_slot\":\"001\",\"product_detect\":\"1\"}"
```

Local without tunnel: replace host with `http://127.0.0.1:5003`.
