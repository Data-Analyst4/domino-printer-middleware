# Domino Ax-Series — Manual Study & Live Test Log

**Canonical log location:** `C:\domino-printer-middleware\docs\`  
**This file:** `docs\DOMINO_STUDY_AND_TEST_LOG.md`

Living document. All printer tests, results, and manual findings are written here (not elsewhere). Updated after each printer test and after each major Q&A from the Domino manuals.

---

## Table of contents

1. [Site / printer identity](#site--printer-identity)
2. [Source manuals](#source-manuals-studied)
3. [Part A — Manual study (full)](#part-a--manual-study-full)
4. [Part B — Live test log](#part-b--live-test-log)
5. [Part C — Limited batch 200/300](#part-c--how-to-send-a-limited-batch-200--300-labels-in-detail)
6. [Part D — Print STOP and RESUME](#part-d--print-stop-and-resume-detailed)
7. [Part E — Quick reference cheat sheet](#part-e--quick-reference-cheat-sheet)
8. [Part F — Middleware vs raw TCP](#part-f--middleware-vs-raw-tcp)
9. [Part G — Running conclusions](#part-g--running-conclusions)
10. [Part H — Update rule](#part-h--update-rule)

---

## Site / printer identity

| Item | Detail |
|------|--------|
| Printer IP | `192.168.1.40` |
| Subnet (from UI) | `255.255.255.0` |
| Hostname (from UI) | `COMPACT` |
| Codenet TCP | Port **`7000`** (also available: 7001, 7002, 7004) |
| Web UI | `http://192.168.1.40/#/home` |
| Middleware | `http://127.0.0.1:5003` |
| Middleware printer ID | `DOMINO_AX_1` |
| Active label (UI / named) | **`NOICE KM 200ML`** |
| Typical FIFO test data | `11/08/2026,10/05/2027,KFBNIKHIL7,158.00/0.79` |
| Protocol settings (confirmed UI) | Codenet, TCP, port 7000, Variable, On processed, **Protocol enabled** |

Config (`config/printers.json` at time of tests):

```json
{
  "DOMINO_AX_1": {
    "ip": "192.168.1.40",
    "port": 7000,
    "protocol": "domino_ax_codenet",
    "default_label_slot": "001",
    "default_product_detect": "1",
    "enabled": true,
    "label_map": { "SKU001": "001", "SKU002": "002" }
  }
}
```

**Note:** Live template in use is the **named** label `NOICE KM 200ML`, not necessarily numeric slots `001`/`002`.

---

## Source manuals (studied)

| File | Part No. | Issue | Pages | Local extract |
|------|----------|-------|-------|---------------|
| `Ax Series Codenet Protocol.pdf` | EPT033760 | Issue 2, Sep 2017 | 196 | `docs/_pdf_extract/Ax_Series_Codenet_Protocol.txt` |
| `772433789-Ax-Series-Product-Manual-EPT019297-4-1.pdf` | EPT019297 | Issue 4, Feb 2019 | 267 | `docs/_pdf_extract/772433789-Ax-Series-Product-Manual-EPT019297-4-1.txt` |

Original download paths:

- `c:\Users\HP\Downloads\Domino\Ax Series Codenet Protocol.pdf`
- `c:\Users\HP\Downloads\Domino\772433789-Ax-Series-Product-Manual-EPT019297-4-1.pdf`

**Codenet manual structure:** Description → Setup → Init → Control → Status → Format → Label format → NAK codes → Extended commands.

**Product manual focus for integration:** Start/Stop/Ready, production line / photocell, External data fields, Codenet protocol setup, consumables UI, File Manager / Label Finder.

---

## Part A — Manual study (full)

### A1. Codenet framing

Every host→printer command:

```text
ESC (1B) + command-id + parameters/payload + EOT (04)
```

| Direction | Pattern |
|-----------|---------|
| Host → printer | `1B … 04` |
| Printer → host | `ACK 06` **or** `NAK 15` + 3 ASCII digits (+ optional query echo) |

| Byte | Hex | Role |
|------|-----|------|
| ESC | `1B` | Start of command |
| EOT | `04` | End — printer **stops listening**; bytes after EOT are **lost** |
| ACK | `06` | Success (Variable mode: 1 byte) |
| NAK | `15` | Failure + `xxx` code |

**Response Length (UI Protocol settings):**

| Mode | ACK | NAK |
|------|-----|-----|
| **Variable** (this site) | `06` | `15` + 3 digits |
| **Fixed** | `06 30 30 30` | `15` + 3 digits |

**Send Response timing:**

| Mode | Behaviour |
|------|-----------|
| **On Processed** (this site — preferred) | ACK/NAK after command processed |
| **On Received** | Early ACK — data not fully validated yet |

**Command families:**

- Single-byte IDs: `A`, `N`, `P`, `Q`, `R`, `S`, `T`, `y`, `[`, …
- Extended `O*`: `OE`, `OP`, `ON`, `OM`, `OQ`, `OS`, `O1`, …
- Codenet 2 `}*` (`7D`): `}D`, `}J`, `}H`, `}F`/`}`G` (latter under development in Issue 2)

**TCP setup (Product + Protocol manuals):**

1. `Home > Setup > Printer network > Protocol settings`
2. Protocol = **Codenet**, Mode = **TCP**, Port = **7000**
3. Tick **Protocol enabled**
4. Restart after changes
5. Needs Basic Comms / Ethernet pack

---

### A2. Start / Stop / Ready (Product Manual)

| Control | Effect |
|---------|--------|
| UI **Start** | Sequence jet **on** → **Ready** |
| UI **Stop** | Options: Sequence off / Pause printing / Jet running / Phase locked |
| Cabinet **Start/Stop** | Ready ↔ Idle |
| Cabinet **Single Print** | One test print (not photocell) |

**Ready + label on-line + print enabled** → photocell prints.

| Status (approx) | Meaning |
|-----------------|---------|
| Idle | Jet off — will not print |
| Sequencing On/Off | Transition |
| Ready | Can print on product detect |
| Pause printing | Jet may run; printing paused |

Codenet jet sequence:

| Action | Hex |
|--------|-----|
| Ready `OS 1` | `1B4F533104` |
| Standby `OS 0` | `1B4F533004` |
| Query `OS ?` | `1B4F533F04` |

---

### A3. Production line / photocell (Product Manual)

Path: `Home > Setup > Production line setup > Print trigger`

| Setting | Role |
|---------|------|
| Trigger by | Internal distance vs **External** photocell |
| Active level | High / Low |
| Print delay (mm) | Distance after detect before print |
| Product detect persistence | Debounce |
| **Product queue depth** | How many in-flight **product** triggers (not the same as FIFO data queue) |

**Product queue** = photocell events in flight.  
**External data / FIFO queue** = variable field packets waiting to print.

---

### A4. Full command catalogue (integration-critical)

#### Identity / version / status

| Purpose | ASCII | Hex example |
|---------|-------|-------------|
| Identify | `A?` | `1B413F04` |
| Codenet version | `}D?` | `1B7D443F04` |
| Extended status (alert+LED) | `O1?` | `1B4F313F04` |
| Basic current status | `1 C ?` | `1B31433F04` |
| Liquid levels (ink + make-up) | `y?` | `1B793F04` |
| Product count query | `T1?` / `T2?` | `1B54313F04` / `1B54323F04` |
| Product count reset | `T1 0` | `1B54313004` |
| Connection count | `}H?` | see manual |

**Liquid levels `y`:** response `ESC y <ink3> <makeup3> EOT`. Typical codes `000`–`008`; `021` = sensor unplugged.

**Product counts `T`:** 10-digit value. Manual warning: count is **photocell transitions**, not always exact codes printed (jet may be off). Counter 2 = “prints since power on” (may be non-resettable).

**O1 useful status codes (examples):** `000` no alert, `001` ready, `002` sequencing on, `003` sequencing off, `009` standby, `011` fault, …

#### Label select / store / create

| Purpose | ASCII | Hex / format |
|---------|-------|----------------|
| Put numeric slot online | `P` | `ESC P 1 SSS EOT` e.g. slot 009 → `1B503130303904` |
| Query online | `P1?` | `1B50313F04` |
| Named label online | `ON` | `ESC ON 1 <len2> <name> EOT` |
| Store named label | `OM` | see manual |
| Store numeric label | `S` | `ESC S SSS <label_data> EOT` |
| Download without save | `OQ` | `ESC OQ SSS <data> EOT` |
| Clear all labels offline | `R` | `1B5204` |

**Create template from PC:** possible via `S` / `OM` / `OQ`, but real layouts need embedded format commands (fonts, barcodes, `|` external fields). Factory templates are normally built in Domino **Label Creator**; middleware then selects + feeds data.

**Check template exists:** try `P` (slot) or `ON` (name) → **ACK** = available; NAK `016`/`017`/`008` = not. No “list all labels” command in these manuals. UI: Label Finder / File Manager.

#### Print trigger / head / continuous

| Purpose | ASCII | Hex |
|---------|-------|-----|
| Print Go (1 pulse) | `N1` | `1B4E3104` |
| Head enable | `Q1Y` | `1B51315904` |
| Head disable (soft stop) | `Q1N` | `1B51314E04` |
| Head query | `Q1?` | `1B51313F04` |
| Continuous off | `[1N` + pitch | `1B5B314E343030303004` (example) |
| Continuous on | `[1Y` + pitch | see manual |
| Auto-repeat | `G` | see manual |
| Print Go delay | `F` | see manual |
| Print acknowledgement char | `I` | char after each printed label |

#### FIFO / external data

| Purpose | ASCII | Hex / notes |
|---------|-------|-------------|
| Configure FIFO | `OP` | STX/ETX, block length, ACK on data, duplicates, clear-on-label-change |
| Send data block | `OE` | `1B4F45` + 4-digit length (`0001`–`1024`) + ASCII data + `04` |
| Clear via OE len 0000 | `OE` | `0`=TCP, `1`=RS232, `2`=historic |
| Reset FIFO | `}J` | Ethernet `1B7D4A3104`; RS232 `…30…` |
| Set/query FIFO size/count | `}F` / `}G` | **Under development** in Issue 2 — do not rely on |

Example send `ABCD`:

```text
1B4F45303030344142434404
```

**External data fields** (Product Manual): Label Creator → Variable → External data → Source Ethernet, Length, Offset, Delimiter, Index (for comma-separated multi-field packets).

Unicode path: stream to Ethernet data port **16000** (not OE ASCII).

---

### A5. FIFO behaviour (manuals + our tests)

| Topic | Detail |
|-------|--------|
| Per-packet size | OE length 1–1024 bytes |
| Queue depth | Can be multi-packet (GPI depth 4–1023); site tests behave like **~1 deep** |
| Cannot read back buffer text | No Codenet “get FIFO contents” |
| Buffer full signal | UI “Buffer empty”; OE NAK; alerts — **NAK 000 is documented as software error**, not officially “full” |
| Clear before new job | Recommended (`}J` or `OE 0000…`) |

**Correct discrete coding loop:**

```text
Ready + template online + head enabled + continuous OFF
→ clear FIFO
→ OE row → ACK
→ photocell or N → print consumes row
→ OE next → …
→ Q N / OS 0 when stopping
```

---

### A6. NAK codes (important)

| Code | Meaning |
|------|---------|
| 000 | Software error (“should never occur”) |
| 001 | Invalid command length |
| 002 | ESC expected |
| 003 | Unrecognised command |
| 004 | Unexpected characters before EOT |
| 005 | Invalid head selector |
| 007 | Parameter out of range |
| 008 | Print label number out of range |
| 009 | Syntax error |
| 010 | Label too long for store |
| 011 | Label too long for print buffer |
| 016 | Cannot load label |
| 017 | Invalid print label number |
| 020 | Command not implemented |
| 027 | Printing disabled |
| 050 | Busy auto-repeat / photocell |
| 051 | Internal printer error |
| 052 | Requested file not found |

---

### A7. Creating labels from middleware

| Capability | Support |
|------------|---------|
| Store simple ASCII label `store_label` / `S` | Yes in middleware |
| Download without save `OQ` | Yes in middleware |
| Full template with fonts/barcodes/`|` fields | Possible in theory with embedded format bytes; **practical** = design on Domino UI |
| Named template `NOICE KM 200ML` | Exists on printer; load with `ON` (raw; not yet middleware action) |

---

## Part B — Live test log

Standard FIFO payload used in most tests:

```text
11/08/2026,10/05/2027,KFBNIKHIL7,158.00/0.79
```

Field mapping (4 external fields on label preview):

| Index | Example value |
|-------|----------------|
| 1 | `11/08/2026` |
| 2 | `10/05/2027` |
| 3 | `KFBNIKHIL7` |
| 4 | `158.00/0.79` |

---

### Test 2026-08-11 — Initial connectivity (Codenet disabled)

| Step | Result |
|------|--------|
| Middleware `/health` | OK v1.0.0 |
| Ping `192.168.1.40` | OK |
| TCP 7000 / 7001 / 7002 / 7004 | **CLOSED** |
| Port 80 | OPEN |
| `/test/connection` | `ready_for_print: false` |
| identify / status / labels | `connect_error` |

**Cause:** Protocol enabled unchecked. Only web UI reachable.

---

### Test 2026-08-12 — UI config review

| Setting | Value |
|---------|--------|
| Protocol | Codenet |
| Protocol enabled | First unchecked → then **checked** |
| Mode | TCP |
| TCP port | 7000 |
| Response length | Variable |
| Send response | On processed |
| IP | 192.168.1.40 |
| DHCP | false |
| WebServer | Enabled |
| UI status | Ready; Buffer empty; product `NOICE KM 200ML` |

---

### Test 2026-08-12 — After Protocol enabled

| Step | Result |
|------|--------|
| Ping | OK (&lt;1 ms) |
| Port 80 | OPEN |
| Port 7000 | **OPEN** |
| `/test/connection` | **`ready_for_print: true`** |
| Identify | Success — response includes Ax identity payload |

---

### Test 2026-08-12 — First FIFO send

| Step | Result |
|------|--------|
| `send_fifo_data` | **success**, ACK `06` |
| Job ID | `509cc801-bec3-45f8-9f25-1975fd66a2e1` |

---

### Test 2026-08-12 — Send 3 identical FIFO rows

| # | Result |
|---|--------|
| 1 | **ACK** (`8846e596…`) |
| 2 | NAK `000` |
| 3 | NAK `000` |

**Conclusion:** Cannot stack identical/unconsumed OE rows; FIFO effectively one pending record.

---

### Test 2026-08-12 — Send 10 FIFO only (multiple attempts)

| Condition | Accepted |
|-----------|----------|
| Buffer empty | **1/10** (first ACK, rest NAK) |
| Buffer full | **0/10** |

**Conclusion:** Domino does **not** queue 10 OE for automatic one-by-one print with current setup.

---

### Test 2026-08-12 — Successful FIFO totals (job log)

Across session, **3** FIFO ACKs recorded at various times (same payload), many NAK `000` on retries while full.

---

### Test 2026-08-12 — Stop printing via Codenet

| Command | Hex | Result |
|---------|-----|--------|
| Disable continuous | `1B5B314E343030303004` | ACK |
| Disable head `Q N` | `1B51314E04` | ACK |
| Query continuous | `1B5B3F04` | `…N00000…` (off) |
| Query head | `1B51313F04` | `…N…` (disabled) |

---

### Test 2026-08-12 — 10 discrete prints (not continuous)

Prep each run: continuous OFF, head ENABLE `Q Y` (`1B51315904`).

Loop ×10: `send_fifo_data` + `print_go`.

| Run | FIFO | print_go |
|-----|------|----------|
| First | 1 OK / 9 FAIL | **10/10 OK** |
| Later repeats | **0/10** | **10/10 OK** |

**Conclusion:** Discrete `N` works for 10 triggers. New FIFO data only when buffer free.

---

### Test 2026-08-12 — Buffer contents / next print count

| Question | Answer |
|----------|--------|
| Read buffer text over Codenet? | **No** |
| Probe same OE while full | NAK `000` → has data |
| Last known payload | `11/08/2026,10/05/2027,KFBNIKHIL7,158.00/0.79` |
| How many prints next? | **1** |

---

### Test 2026-08-13 — Ping / live check

| Step | Result |
|------|--------|
| Ping | OK 0% loss |
| Port 80 / 7000 | OPEN |
| `/test/connection` | **`ready_for_print: true`**, identify OK |

**Verdict:** Printer live.

---

### Test 2026-08-13 — Template `NOICE KM 200ML` available?

| Check | Result |
|-------|--------|
| `ON` name=`NOICE KM 200ML` len=`14` | **ACK `06` — AVAILABLE** |
| Hex sent | `1B4F4E3131344E4F494345204B4D203230304D4C04` |
| Query `P1?` | `1B50314E4F4904` (name-related online state) |
| Middleware `put_label_online` 001 / 002 | NAK `004` |

**Verdict:** Named template **exists and loads**. Numeric slots 001/002 are not this template’s identity.

---

### Test 2026-08-13 — Status + FIFO probe

| Check | Result |
|-------|--------|
| `get_status` O1 | OK — status **`001` Ready**, LED `01` |
| `get_basic_status` | OK |
| `identify` | OK |
| FIFO probe data=`PROBE` | **ACK** (buffer was empty) |

**Note:** `PROBE` may remain in FIFO until printed or cleared with `}J`.

---

### Test 2026-08-13 — Ink / make-up levels

| Item | Value |
|------|--------|
| Command | `y?` → `1B793F04` |
| Raw response | `1B7930303730303604` |
| **Ink** | **`007`** (scale typically 000–008) |
| **Make-up** | **`006`** |
| Middleware | Not implemented (raw TCP) |

---

### Test 2026-08-13 — Product / print counts

| Counter | Query hex | Value |
|---------|-----------|-------|
| T1 | `1B54313F04` | **304,641,327** |
| T2 | `1B54323F04` | **138** |

Manual: photocell transitions ≠ guaranteed inked codes. Middleware action not implemented yet.

---

## Part C — How to send a limited batch (200 / 300 labels) in detail

### C1. Meaning of “limited data”

Fixed list of **N** rows (200 or 300). Each row is one `OE` packet for External data fields.  
**N is enforced by ERP/host loop**, not by a Domino “max 200” command.

### C2. Two queues

| Queue | Holds | Sized by |
|-------|--------|----------|
| Host | All N rows | Your software |
| Printer FIFO | Next print’s data | Domino (~1 deep here; can be raised 4–1023) |

### C3. Flow

```text
PREP: Ready, Q Y, continuous OFF, ON template, }J clear
LOOP i = 1 .. N:
  send_fifo_data(rows[i]) → wait ACK
  wait print (photocell or print_go) → wait ACK / complete
END when i == N
optional: }J, Q N / OS 0
```

### C4. Middleware JSON

```json
{ "printer_id": "DOMINO_AX_1", "action": "send_fifo_data", "data": "..." }
{ "printer_id": "DOMINO_AX_1", "action": "print_go", "product_detect": "1" }
```

### C5. Line vs PC trigger

| Mode | Print trigger |
|------|----------------|
| Production | Photocell — host only feeds OE when previous consumed |
| Lab / no PD | `print_go` after each OE |

### C6. Errors in loop

| Event | Action |
|-------|--------|
| OE ACK | Proceed to print wait |
| OE NAK | Retry / wait / `}J` — do not advance index |
| print_go NAK 027 | `Q Y` / Ready |
| Done N rows | Stop — that is the limit |

### C7. Wrong vs right

| Wrong | Right |
|-------|--------|
| 300× OE with no print | OE → print → OE → … × N |
| Expect auto-drain of 10 OE | Host paces on consume |

---

## Part D — Print STOP and RESUME (detailed)

No single command named STOP/RESUME. Use levels:

| Level | Stop | Resume |
|-------|------|--------|
| Soft pause | `Q N` `1B51314E04` | `Q Y` `1B51315904` |
| Continuous off | `[ N …` | `[ Y …` or stay OFF |
| Jet standby | `OS 0` `1B4F533004` | `OS 1` `1B4F533104` |
| Label offline | `R` `1B5204` | `ON` / `P` |
| UI | Stop | Start |

**Recommended production pause:** `Q N` (+ stop sending OE).  
**Resume:** `Q Y` (+ `OS 1` if not Ready).  
**Abort leftover data:** `Q N` + `}J`.  
**Pause only:** keep FIFO; **abort:** clear FIFO.

Query head: `1B51313F04`.  
GPIO: Print enable / Print abort if wired.

Middleware: `stop_printing` / `resume_printing` **not implemented** yet (raw TCP works — tested).

---

## Part E — Quick reference cheat sheet

| Need | How |
|------|-----|
| Ping / live? | ICMP + TCP 7000 + `/test/connection` |
| Status | `get_status` / `O1?` |
| Ink / make-up | `1B793F04` |
| Print count | `T1?` / `T2?` |
| Template exists? | `ON` name or `P` slot → ACK |
| Load `NOICE KM 200ML` | `1B4F4E3131344E4F494345204B4D203230304D4C04` |
| Send field data | `send_fifo_data` / `OE` |
| One print | `print_go` / `N` or photocell |
| Clear FIFO | `1B7D4A3104` |
| Stop print | `1B51314E04` |
| Resume print | `1B51315904` |
| Jet Ready / Standby | `1B4F533104` / `1B4F533004` |
| Continuous OFF | `1B5B314E343030303004` |
| Limited 200/300 | Host loop N× (OE → print) |

---

## Part F — Middleware vs raw TCP

### Implemented `/print` actions

| Action | Codenet |
|--------|---------|
| `identify` | `A?` |
| `get_codenet_version` | `}D?` (NAK 003 on this site — do not use) |
| `get_status` / `get_extended_status` | `O1?` |
| `get_basic_status` | `1C?` |
| `put_label_online` | `P` + slot |
| `put_named_label_online` | `ON` + length + name |
| `query_online_label` | `P1?` |
| `print_go` | `N` (legacy slot path only) |
| `print_stored_label` | `P` then `N` |
| `print_product` | map SKU → slot then print |
| `send_fifo_data` / `push_fifo_fields` | `OE` (no `N`) |
| `soft_stop` | `Q1N` |
| `soft_resume` | `Q1Y` |
| `store_label` | `S` |
| `download_label_without_save` | `OQ` |

### Connection helpers

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | Middleware up |
| `GET /printers` | Configured printers |
| `POST /test/ping` | ICMP |
| `POST /test/port` | TCP open |
| `POST /test/connection` | Ping + port + identify |
| `GET /jobs` | Recent jobs |

### Not yet in middleware (use raw `192.168.1.40:7000`)

| Feature | Command |
|---------|---------|
| Continuous on/off | `[` |
| Jet Ready/Standby | `OS` |
| Reset FIFO (`}J`) | unsupported here — use `OE` len `0000` instead |
| Liquid levels | `y` |
| Product counts | `T` |
| Clear labels offline | `R` |

---

## Part G — Running conclusions

1. Codenet on `192.168.1.40:7000` works when **Protocol enabled**.
2. Variable coding path = **`OE` + print consume** (photocell or `N`).
3. Do **not** blast many `OE` without print — expect NAK until buffer frees (~1 deep here).
4. Continuous `[` ≠ discrete coding; keep OFF unless intentional.
5. Soft stop/resume = **`Q N` / `Q Y`**; stronger = **`OS 0` / `OS 1`**.
6. Template **`NOICE KM 200ML`** is **available** via **`ON`**.
7. Clear FIFO with **`}J`** before new batches.
8. Limited **200/300** = host paced loop; not one Domino dump.
9. Ink/make-up readable via **`y`**; counts via **`T`** (photocell caveat).
10. Buffer text cannot be read back; probe OE or UI “Buffer empty”.

---

## Part H — Update rule

After **every** live printer test or new manual finding, update this file:

1. Append a dated subsection under **Part B** (command, hex, ACK/NAK, conclusion).
2. If it is a new capability (ink, counts, stop, batch, …), expand **Part A / C / D / E / F** as needed.
3. Bump **Last updated** below.

---

*Last updated: 2026-08-21 — ERP photocell actions (`ON` / `P1?` / `OE` / `Q`) wired to HTTP; no live Ax retest this date.*
