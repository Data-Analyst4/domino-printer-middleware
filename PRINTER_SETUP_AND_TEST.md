# Domino Printer Setup + Connection Test

How to configure the Domino Ax printer for TCP/Codenet, then prove the link with ping → port → Codenet → print.

---

## 1. Configure Domino printer (TouchPanel)

### Network / IP

1. Set a **fixed IP** on the Domino printer (same LAN as the middleware PC).
2. Note: IP, subnet, gateway.
3. Middleware PC should also use a fixed IP on that LAN.

### Codenet TCP (required for this app)

Path (typical):

```text
Home > Setup > Printer network > Advanced
```

Set:

| Setting | Value |
|---------|--------|
| Protocol Setting | **Codenet** |
| Protocol Mode | **TCP** |
| Protocol Enabled | **On / Enabled** |
| TCP Port | **7000** (or 7001 / 7002 / 7004) |
| Response timing | **On Processed** (recommended) |
| Response length | **Variable** (unless site uses Fixed ACK) |

Then **restart** the printer after protocol changes.

Needs: **Basic Comms** Ethernet pack on the printer.

### Label ready to print

1. Create / open a label on Domino.
2. Save it in label store (e.g. slot `001`).
3. For variable batch lines later: add **updatable text fields** (Domino POD equivalent).
4. Ensure jet is ready / ink jet sequenced for a real print test.

---

## 2. Configure Domino middleware

Edit `domino/config/printers.json`:

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

Start app:

```powershell
cd domino
python main.py
```

Default listen: `http://0.0.0.0:5003`

---

## 3. Test in order (ping → port → Codenet → print)

Replace IP with your Domino IP.

### A) Ping (ICMP reachability)

```powershell
curl -X POST http://127.0.0.1:5003/test/ping -H "Content-Type: application/json" -d "{\"ip\":\"192.168.1.50\"}"
```

Or by configured printer:

```json
{ "printer_id": "DOMINO_AX_1" }
```

Expect `"reachable": true`.

### B) TCP IP:port (Codenet listener)

```powershell
curl -X POST http://127.0.0.1:5003/test/port -H "Content-Type: application/json" -d "{\"ip\":\"192.168.1.50\",\"port\":7000}"
```

Expect `"open": true`.

If ping works but port fails: Codenet not enabled, wrong port, firewall, or printer not restarted.

### C) Full connection test (ping + port + Codenet identify)

```powershell
curl -X POST http://127.0.0.1:5003/test/connection -H "Content-Type: application/json" -d "{\"printer_id\":\"DOMINO_AX_1\",\"printer\":{\"ip\":\"192.168.1.50\",\"port\":7000}}"
```

This sends Codenet identify `1B413F04`.  
Expect `"ready_for_print": true` and identify `success: true`.

### D) Send print data / trigger print

Identity only:

```json
POST /print
{ "printer_id": "DOMINO_AX_1", "action": "identify" }
```

Status:

```json
{ "printer_id": "DOMINO_AX_1", "action": "get_status" }
```

Print stored label (physical print):

```json
{
  "printer_id": "DOMINO_AX_1",
  "action": "print_stored_label",
  "label_slot": "001",
  "product_detect": "1"
}
```

Send FIFO batch values (after updatable fields exist on label):

```json
{
  "printer_id": "DOMINO_AX_1",
  "action": "send_fifo_data",
  "data": "BATCH-001,MFG:23-07-2026,EXP:23-01-2027,MRP:95.00"
}
```

Then `print_stored_label` as above.

---

## 4. What “good” looks like

| Step | Good result |
|------|-------------|
| Ping | `reachable: true` |
| Port 7000 | `open: true` |
| Identify | `success: true`, response hex present |
| Print | `success: true`, steps ACK (`06`) |

---

## 5. Common failures

| Symptom | Fix |
|---------|-----|
| Ping fails | Wrong IP / VLAN / cable; PC and printer not on same LAN |
| Ping OK, port closed | Enable Codenet TCP 7000; restart printer; check Windows firewall |
| Port OK, identify fails | Protocol not Codenet; wrong response mode; another client holding the port |
| Identify OK, print NAK | Label slot missing; printing disabled; jet not ready |

---

## 6. ERP / UI flow (same idea)

1. Save Domino IP + port `7000` on printer master.  
2. Button **Test ping** → `POST /test/ping`  
3. Button **Test connection** → `POST /test/connection`  
4. Only if `ready_for_print` → allow **Print** → `POST /print`
