# Domino Command Probe Log

Step-by-step live probe: **one command at a time**.  
User confirms printer UI / next action after each step.

| Item | Value |
|------|--------|
| Printer | `192.168.1.40` |
| Port | `7000` (Codenet TCP) |
| How | Raw TCP socket — send binary frame `ESC … EOT`, read reply |
| Middleware | Not used for these probe steps unless noted |
| Started | 2026-08-13 |

---

## Planned sequence

| # | Status | Command | Purpose (why we send it) |
|---|--------|---------|--------------------------|
| 1 | **DONE** | Identify `A?` | Prove Codenet link; read printer identity / type |
| 2 | **DONE** | Extended status `O1?` | Read Ready/fault alert code + cabinet LED state |
| 3 | **DONE** | Basic status `1C?` | Read short status + jet id + status-change time |
| 4 | **DONE** | Codenet version `}D?` | Read Codenet protocol version (unsupported here → NAK 003) |
| 5 | **DONE** | Liquid levels `y?` | Read ink and make-up level codes |
| 6 | **DONE** | Head enable query `Q1?` | Check if printing is allowed (`Y`) or soft-stopped (`N`) |
| 7 | **DONE** | Continuous query `[?` | Check if continuous print mode is ON or OFF |
| 8 | **DONE** | Product count T1 | Read product/photocell counter 1 |
| 9 | **DONE** | Product count T2 | Read counter 2 (often prints since power-on) |
| 10 | **DONE** | Named label `ON` | Confirm/load template **NOICE KM 200ML** online |
| 11 | **DONE** | Query online `P1?` | See which label is currently online |
| 12 | **DONE** | Head disable `Q1N` | Soft **STOP** printing (inhibit prints) |
| 13 | **DONE** | Head enable `Q1Y` | Soft **RESUME** printing |
| 14 | **DONE** | Clear FIFO `}J` | Delete queued external/FIFO data |
| 15 | **DONE** | FIFO data `OE` | Load variable field data for next print (needs your OK) |
| 16 | **DONE** | Print Go `N` | Trigger one print pulse (needs your OK) |

---

## Step 1 — Identify printer

### Purpose

**Purpose:** Verify the PC can talk Codenet to the printer and read the printer identity string (link + identity check). Does not print and should not change the UI.

### Where
- **IP:** `192.168.1.40`
- **Port:** `7000`
- **Protocol:** Codenet over TCP
- **Transport:** Python `socket.create_connection` → `sendall` → `recv`

### How we send
1. Open TCP connection to `192.168.1.40:7000`
2. Send exact bytes of command frame
3. Read response bytes
4. Close connection

### What we send

| Field | Value |
|-------|--------|
| Command | Identify query `A?` |
| ASCII meaning | `ESC` + `A` + `?` + `EOT` |
| Hex sent | `1B413F04` |
| Bytes | `0x1B 0x41 0x3F 0x04` |

### What we received

| Field | Value |
|-------|--------|
| Time (UTC) sent | `2026-08-13T10:41:50.699688+00:00` |
| Time (UTC) recv | `2026-08-13T10:41:50.746983+00:00` |
| Raw hex received | `1B41303135363036373036303004` |
| ACK (06)? | `False` |
| NAK code | `None` |
| Framed query payload (inside ESC…EOT) | `413031353630363730363030` |
| Payload ASCII (best-effort) | `A01560670600` |

### Interpretation

- Command **Identify** (`A?`) completed over TCP `192.168.1.40:7000`.
- Printer returned a **framed query response** (not a bare ACK), which is normal for identify.
- Inner payload starts with `A` (command echo) then identity digits (Ax-Series type often includes `30`).

### Notes / user observation

**Domino UI after Step 1 (user screenshot, ~16:17 | 13 Aug 2026):**

| UI element | Observed |
|------------|----------|
| Top STATUS | **Ready** (green) |
| START | Greyed out |
| STOP | Active (available) |
| Footer | **Ready** · Ax Series · **NOICE KM 200ML** |
| Preview | Four lines of placeholder `C` characters (external/updatable fields) |
| Ink / make-up icons | Green bars (looks full / OK) |
| Visible change from Identify command? | **None expected** — Identify is a query only; UI stayed Ready with same template |

Identify (`A?`) does not change screen state; it only returns identity over TCP (which we got: `A01560670600`).

---

**Next:** Step 2 sent — see below.

---

## Step 2 — Extended status (`O1?`)

### Purpose

**Purpose:** Read high-level printer state used for dashboards — alert/status code (e.g. Ready `001`) and LED state. Confirms Ready vs fault without touching print.

### Where
- **IP:** `192.168.1.40`
- **Port:** `7000`
- **Protocol:** Codenet over TCP
- **Transport:** Raw TCP socket `sendall` → `recv`

### How we send
1. Open TCP `192.168.1.40:7000`
2. Send command bytes
3. Read response
4. Close connection

### What we send

| Field | Value |
|-------|--------|
| Command | Extended current status query `O1?` |
| ASCII meaning | `ESC` + `O1` + `?` + `EOT` |
| Hex sent | `1B4F313F04` |
| Bytes | `0x1B 0x4F 0x31 0x3F 0x04` |

### What we received

| Field | Value |
|-------|--------|
| Time (UTC) sent | `2026-08-13T10:50:50.129964+00:00` |
| Time (UTC) recv | `2026-08-13T10:50:50.250090+00:00` |
| Raw hex received | `1B4F31303031303104` |
| ACK (06)? | `False` |
| NAK code | `None` |
| Payload ASCII | `O100101` |
| Status code (3 digits) | `001` → **ready** |
| LED state (2 digits) | `01` |

### Interpretation

- `O1` returns printer status + cabinet LED state.
- Status `001` = **ready** (matches UI **Ready** if `001`).
- This is a query only — UI should not change.

### Notes / user observation

User said **send 3**.

---

## Step 3 — Basic status (`1C?`)

### Purpose

**Purpose:** Read the classic status report (status class, ink-jet id, last status-change time HHMM). Complements `O1` with timing detail.

### Where
- **IP:** `192.168.1.40`
- **Port:** `7000`
- **Protocol:** Codenet over TCP
- **Transport:** Raw TCP socket `sendall` → `recv`

### How we send
1. Open TCP `192.168.1.40:7000`
2. Send command bytes
3. Read response
4. Close connection

### What we send

| Field | Value |
|-------|--------|
| Command | Basic / current status request `1 C ?` |
| ASCII meaning | `ESC` + `1` + `C` + `?` + `EOT` |
| Hex sent | `1B31433F04` |
| Bytes | `0x1B 0x31 0x43 0x3F 0x04` |

### What we received

| Field | Value |
|-------|--------|
| Time (UTC) sent | `2026-08-13T10:51:54.763045+00:00` |
| Time (UTC) recv | `2026-08-13T10:51:54.816180+00:00` |
| Raw hex received | `1B3143303030313136313904` |
| ACK (06)? | `False` |
| NAK code | `None` |
| Payload ASCII | `1C00011619` |
| Status (3 digits) | `000` |
| Ink-jet id digit | `1` |
| Status change time (HHMM) | `1619` |

### Interpretation

- Basic status (`1C`) returns a short status report (status class + jet id + time).
- Query only — UI should not change.
- Complements Step 2 `O1` (alert + LED).

### Notes / user observation

User said **send 4**.

---

## Step 4 — Codenet version (`}D?`)

### Purpose

**Purpose:** Ask the printer which Codenet version it speaks. Useful for capability checks; on this unit it returned NAK 003 (command not recognised).

### Where
- **IP:** `192.168.1.40`
- **Port:** `7000`
- **Protocol:** Codenet over TCP
- **Transport:** Raw TCP socket `sendall` → `recv`

### How we send
1. Open TCP `192.168.1.40:7000`
2. Send command bytes
3. Read response
4. Close connection

### What we send

| Field | Value |
|-------|--------|
| Command | Codenet version query `}D?` |
| ASCII meaning | `ESC` + `}` + `D` + `?` + `EOT` |
| Hex sent | `1B7D443F04` |
| Bytes | `0x1B 0x7D 0x44 0x3F 0x04` |

### What we received

| Field | Value |
|-------|--------|
| Time (UTC) sent | `2026-08-13T10:52:45.598514+00:00` |
| Time (UTC) recv | `2026-08-13T10:52:45.643250+00:00` |
| Raw hex received | `15303033` |
| ACK (06)? | `False` |
| NAK code | `003` |
| Payload ASCII | `None` |
| Version (3 chars) | `None` |

### Interpretation

- Printer returned **NAK `003`** = Unrecognised command code following ESC.
- On this firmware/build, `}D` (Codenet version query) appears **not supported** or not enabled.
- Hex `15303033` = `NAK` + ASCII `003`.
- Query failed — UI should still be unchanged (Ready).

### Notes / user observation

**Follow-up research (NAK 003 on Step 4):**

| Topic | Detail |
|-------|--------|
| NAK format | `15` + 3 ASCII digits → `15303033` = NAK + **`003`** |
| Manual text (Part 8) | **`003 Unrecognised command code following <ESC>`** |
| Meaning | After `ESC` (`1B`), the printer did **not recognise** the command ID that followed |
| What we sent after ESC | `}D?` = bytes `7D 44 3F` (Codenet 2 double-byte command) |
| Compatibility table (Part 1) | `7D44 }D` listed as **New** for Ax / **Not supported** on older Codenet 1 families |
| Likely cause | This printer’s firmware does **not implement** `}D`, **or** Codenet 2 `}` commands are not enabled on this pack/software build |
| Not a network error | TCP worked; printer actively rejected the command ID |
| Related codes | `020` = Command not implemented (different case); we got **`003`** = unrecognised ID |

User asked what NAK 003 is — documented above. User said **send 5**.

---

## Step 5 — Liquid levels / ink + make-up (`y?`)

### Purpose

**Purpose:** Read consumable levels (ink + make-up) over the network so ERP/middleware can warn before empty — without opening the cabinet.

### Where
- **IP:** `192.168.1.40`
- **Port:** `7000`
- **Protocol:** Codenet over TCP
- **Transport:** Raw TCP socket `sendall` → `recv`

### How we send
1. Open TCP `192.168.1.40:7000`
2. Send command bytes
3. Read response
4. Close connection

### What we send

| Field | Value |
|-------|--------|
| Command | Read Liquid Levels `y?` |
| ASCII meaning | `ESC` + `y` + `?` + `EOT` |
| Hex sent | `1B793F04` |
| Bytes | `0x1B 0x79 0x3F 0x04` |

### What we received

| Field | Value |
|-------|--------|
| Time (UTC) sent | `2026-08-13T11:03:16.648110+00:00` |
| Time (UTC) recv | `2026-08-13T11:03:16.693527+00:00` |
| Raw hex received | `1B7930303730303604` |
| ACK (06)? | `False` |
| NAK code | `None` |
| Payload ASCII | `y007006` |
| Ink (3 digits) | `007` — level code 7 (typical scale 000-008) |
| Make-up (3 digits) | `006` — level code 6 (typical scale 000-008) |

### Interpretation

- Manual: ink + make-up are 3-digit codes, normally `000`–`008`; `021` = sensor unplugged.
- Ink **`007`**, make-up **`006`** — should align with green fluid bars on UI.
- Query only — UI should not change.

### Notes / user observation

User said **send 6**.

---

## Step 6 — Head enable query (`Q1?`)

### Purpose

**Purpose:** Learn whether the print head is enabled (`Y` = may print) or disabled (`N` = soft stop). Needed before stop/resume tests.

### Where
- **IP:** `192.168.1.40`
- **Port:** `7000`
- **Protocol:** Codenet over TCP
- **Transport:** Raw TCP socket `sendall` → `recv`

### How we send
1. Open TCP `192.168.1.40:7000`
2. Send command bytes
3. Read response
4. Close connection

### What we send

| Field | Value |
|-------|--------|
| Command | Head Enable query `Q 1 ?` |
| ASCII meaning | `ESC` + `Q` + `1` + `?` + `EOT` |
| Hex sent | `1B51313F04` |
| Bytes | `0x1B 0x51 0x31 0x3F 0x04` |

### What we received

| Field | Value |
|-------|--------|
| Time (UTC) sent | `2026-08-13T11:03:54.007202+00:00` |
| Time (UTC) recv | `2026-08-13T11:03:54.050438+00:00` |
| Raw hex received | `1B51315904` |
| ACK (06)? | `False` |
| NAK code | `None` |
| Payload ASCII | `Q1Y` |
| Head select | `1` (Ax always `1`) |
| Head enable | `Y` → **ENABLED (printing allowed)** |

### Interpretation

- `Q` reports whether printing is enabled (`Y`) or soft-stopped (`N`).
- Current state: **ENABLED (printing allowed)**.
- Query only — UI should not change (Ready can still show even if head were disabled; print would then NAK 027).

### Notes / user observation

User said **send 7**.

---

## Step 7 — Continuous printing query (`[?`)

### Purpose

**Purpose:** Learn whether continuous pitch-printing mode is ON or OFF. For discrete bottle coding we want OFF.

### Where
- **IP:** `192.168.1.40`
- **Port:** `7000`
- **Protocol:** Codenet over TCP
- **Transport:** Raw TCP socket `sendall` → `recv`

### How we send
1. Open TCP `192.168.1.40:7000`
2. Send command bytes
3. Read response
4. Close connection

### What we send

| Field | Value |
|-------|--------|
| Command | Continuous Printing query `[ ?` |
| ASCII meaning | `ESC` + `[` + `?` + `EOT` |
| Hex sent | `1B5B3F04` |
| Bytes | `0x1B 0x5B 0x3F 0x04` |

### What we received

| Field | Value |
|-------|--------|
| Time (UTC) sent | `2026-08-13T11:04:49.871405+00:00` |
| Time (UTC) recv | `2026-08-13T11:04:49.918928+00:00` |
| Raw hex received | `1B5B314E303030303004` |
| ACK (06)? | `False` |
| NAK code | `None` |
| Payload ASCII | `[1N00000` |
| Head select | `1` |
| Continuous Y/N | `N` → **CONTINUOUS OFF** |
| Label pitch (5 digits) | `00000` |

### Interpretation

- Continuous mode is separate from discrete photocell / `print_go` coding.
- Current state: **CONTINUOUS OFF** (pitch `00000`).
- For FIFO + one-product-at-a-time coding, **OFF** is what we want.
- Query only — UI should not change.

### Notes / user observation

User said **send 8**.

---

## Step 8 — Product count T1 (`T1?`)

### Purpose

**Purpose:** Read product counter 1 (photocell transitions) to track how many triggers the line has seen.

### Where
- **IP:** `192.168.1.40`
- **Port:** `7000`
- **Protocol:** Codenet over TCP
- **Transport:** Raw TCP socket `sendall` → `recv`

### How we send
1. Open TCP `192.168.1.40:7000`
2. Send command bytes
3. Read response
4. Close connection

### What we send

| Field | Value |
|-------|--------|
| Command | Product Counts query counter **1** `T 1 ?` |
| ASCII meaning | `ESC` + `T` + `1` + `?` + `EOT` |
| Hex sent | `1B54313F04` |
| Bytes | `0x1B 0x54 0x31 0x3F 0x04` |

### What we received

| Field | Value |
|-------|--------|
| Time (UTC) sent | `2026-08-13T11:06:47.980992+00:00` |
| Time (UTC) recv | `2026-08-13T11:06:48.063175+00:00` |
| Raw hex received | `1B54313033303436343133323704` |
| ACK (06)? | `False` |
| NAK code | `None` |
| Payload ASCII | `T10304641327` |
| Counter ID | `1` |
| Count (10 digits raw) | `0304641327` |
| Count (integer) | **304641327** |

### Interpretation

- Manual: product counters count **photocell transitions**, not always exact inked codes (jet may be off).
- T1 current value: **304641327**.
- Query only — UI should not change.

### Notes / user observation

User said **send 9**.

---

## Step 9 — Product count T2 (`T2?`)

### Purpose

**Purpose:** Read product counter 2 (often prints since power-on) for a second production count metric.

### Where
- **IP:** `192.168.1.40`
- **Port:** `7000`
- **Protocol:** Codenet over TCP
- **Transport:** Raw TCP socket `sendall` → `recv`

### How we send
1. Open TCP `192.168.1.40:7000`
2. Send command bytes
3. Read response
4. Close connection

### What we send

| Field | Value |
|-------|--------|
| Command | Product Counts query counter **2** `T 2 ?` |
| ASCII meaning | `ESC` + `T` + `2` + `?` + `EOT` |
| Hex sent | `1B54323F04` |
| Bytes | `0x1B 0x54 0x32 0x3F 0x04` |

### What we received

| Field | Value |
|-------|--------|
| Time (UTC) sent | `2026-08-13T11:07:46.033034+00:00` |
| Time (UTC) recv | `2026-08-13T11:07:46.151572+00:00` |
| Raw hex received | `1B54323030303030303031333804` |
| ACK (06)? | `False` |
| NAK code | `None` |
| Payload ASCII | `T20000000138` |
| Counter ID | `2` |
| Count (10 digits raw) | `0000000138` |
| Count (integer) | **138** |

### Interpretation

- Manual: Counter 2 is often **“Prints since power on”** (may be non-resettable depending on config).
- Still based on photocell-style counting caveats.
- T2 current value: **138**.
- Query only — UI should not change.

### Notes / user observation

User said **send 10**.

---

## Step 10 — Named label online (`ON` — NOICE KM 200ML)

### Purpose

**Confirm the print template `NOICE KM 200ML` exists in the printer store and put it online** so the next FIFO/print uses that layout (4 external field lines). This is the named-label equivalent of selecting a template.

### Where
- **IP:** `192.168.1.40`
- **Port:** `7000`
- **Protocol:** Codenet over TCP
- **Transport:** Raw TCP socket `sendall` → `recv`

### How we send
1. Open TCP `192.168.1.40:7000`
2. Send command bytes
3. Read response
4. Close connection

### What we send

| Field | Value |
|-------|--------|
| Command | Get named label from store and put online `ON` |
| Label name | `NOICE KM 200ML` |
| Name length | `14` (ASCII digits) |
| ASCII meaning | `ESC` + `ON` + `1` + `14` + `NOICE KM 200ML` + `EOT` |
| Hex sent | `1B4F4E3131344E4F494345204B4D203230304D4C04` |

### What we received

| Field | Value |
|-------|--------|
| Time (UTC) sent | `2026-08-13T11:15:59.740329+00:00` |
| Time (UTC) recv | `2026-08-13T11:15:59.844892+00:00` |
| Raw hex received | `06` |
| ACK (06)? | `True` |
| NAK code | `None` |
| Result | **AVAILABLE / loaded online (ACK)** |

### Interpretation

- ACK means template **is available** and was put **online**.
- UI may already have shown this template; re-selecting should keep **NOICE KM 200ML** on the footer.
- Not a print trigger — only selects/loads the label.

### Notes / user observation

User said **send 11**.

---

## Step 11 — Query currently online label (`P1?`)

### Purpose

**Ask which label is currently online** after Step 10 loaded `NOICE KM 200ML`. For numeric slots this usually returns a 3-digit slot; for named labels the reply may echo name-related bytes. Used to verify selection without printing.

### Where
- **IP:** `192.168.1.40`
- **Port:** `7000`
- **Protocol:** Codenet over TCP
- **Transport:** Raw TCP socket `sendall` → `recv`

### How we send
1. Open TCP `192.168.1.40:7000`
2. Send command bytes
3. Read response
4. Close connection

### What we send

| Field | Value |
|-------|--------|
| Command | Put-label / online query `P 1 ?` |
| ASCII meaning | `ESC` + `P` + `1` + `?` + `EOT` |
| Hex sent | `1B50313F04` |
| Bytes | `0x1B 0x50 0x31 0x3F 0x04` |

### What we received

| Field | Value |
|-------|--------|
| Time (UTC) sent | `2026-08-13T11:16:42.720205+00:00` |
| Time (UTC) recv | `2026-08-13T11:16:42.764125+00:00` |
| Raw hex received | `1B50314E4F4904` |
| ACK (06)? | `False` |
| NAK code | `None` |
| Payload ASCII | `P1NOI` |

### Interpretation

- Query response for online label selection.
- Payload ASCII: `P1NOI` (may be slot digits or partial name bytes when a named label is online).
- Matches expectation that a label is online after successful `ON` in Step 10.
- Query only — UI should not change.

### Notes / user observation

User said **send 12**.

---

## Step 12 — Soft STOP printing (Head disable `Q1N`)

### Purpose

**Soft-stop / pause printing** by disabling the print head (`Q N`). Photocell and `print_go` should not print while disabled (often NAK `027`). Jet may stay Ready; this is inhibit-print, not full jet standby (`OS 0`). Resume later with Step 13 `Q Y`.

### Where
- **IP:** `192.168.1.40`
- **Port:** `7000`
- **Protocol:** Codenet over TCP
- **Transport:** Raw TCP socket `sendall` → `recv`

### How we send
1. Open TCP `192.168.1.40:7000`
2. Send disable command
3. Read ACK/NAK
4. Close; then query `Q1?` to verify state

### What we send

| Field | Value |
|-------|--------|
| Command | Head Enable **disable** `Q 1 N` |
| ASCII meaning | `ESC` + `Q` + `1` + `N` + `EOT` |
| Hex sent | `1B51314E04` |
| Bytes | `0x1B 0x51 0x31 0x4E 0x04` |

### What we received

| Field | Value |
|-------|--------|
| Time (UTC) sent | `2026-08-13T11:18:51.749217+00:00` |
| Time (UTC) recv | `2026-08-13T11:18:51.803606+00:00` |
| Raw hex received | `06` |
| ACK (06)? | `True` |
| NAK code | `None` |

### Verify query after set (`Q1?` → `1B51313F04`)

| Field | Value |
|-------|--------|
| Verify hex received | `1B51314E04` |
| Verify ASCII | `Q1N` |
| Head enable now | `N` → **DISABLED** |

### Interpretation

- Soft STOP applied: head enable should be **`N`**.
- UI may still show **Ready** (jet running) while printing is inhibited.
- Look for any UI hint that printing is disabled / paused if present.

### Notes / user observation

User said **send 13**.

---

## Step 13 — Soft RESUME printing (Head enable `Q1Y`)

### Purpose

**Resume printing** after Step 12 soft-stop by enabling the print head again (`Q Y`). Photocell / `print_go` may print again if printer is Ready and a label is online.

### Where
- **IP:** `192.168.1.40`
- **Port:** `7000`
- **Protocol:** Codenet over TCP
- **Transport:** Raw TCP socket `sendall` → `recv`

### How we send
1. Open TCP `192.168.1.40:7000`
2. Send enable command
3. Read ACK/NAK
4. Close; then query `Q1?` to verify state

### What we send

| Field | Value |
|-------|--------|
| Command | Head Enable **enable** `Q 1 Y` |
| ASCII meaning | `ESC` + `Q` + `1` + `Y` + `EOT` |
| Hex sent | `1B51315904` |
| Bytes | `0x1B 0x51 0x31 0x59 0x04` |

### What we received

| Field | Value |
|-------|--------|
| Time (UTC) sent | `2026-08-13T11:21:59.570946+00:00` |
| Time (UTC) recv | `2026-08-13T11:21:59.656312+00:00` |
| Raw hex received | `06` |
| ACK (06)? | `True` |
| NAK code | `None` |

### Verify query after set (`Q1?` → `1B51313F04`)

| Field | Value |
|-------|--------|
| Verify hex received | `1B51315904` |
| Verify ASCII | `Q1Y` |
| Head enable now | `Y` → **ENABLED** |

### Interpretation

- Soft RESUME applied: head enable should be **`Y`**.
- Stop/resume pair (Steps 12–13) confirmed working over Codenet.

### Notes / user observation

User said **send 14**.

---

## Step 14 — Clear FIFO / external data queue (`}J`)

### Purpose

**Delete all buffered external/FIFO data** on the Ethernet path so stale field values are not printed. Manual recommends clearing before loading a new batch. Equivalent intent to UI “Buffer empty” / clear EDC queues.

### Where
- **IP:** `192.168.1.40`
- **Port:** `7000`
- **Protocol:** Codenet over TCP
- **Transport:** Raw TCP socket `sendall` → `recv`

### How we send
1. Open TCP `192.168.1.40:7000`
2. Send reset-FIFO command
3. Read ACK/NAK
4. Close connection

### What we send

| Field | Value |
|-------|--------|
| Command | Reset FIFO Data Buffer `}J` (Ethernet = `1`) |
| ASCII meaning | `ESC` + `}` + `J` + `1` + `EOT` |
| Hex sent | `1B7D4A3104` |
| Bytes | `0x1B 0x7D 0x4A 0x31 0x04` |

### What we received

| Field | Value |
|-------|--------|
| Time (UTC) sent | `2026-08-13T11:24:18.086741+00:00` |
| Time (UTC) recv | `2026-08-13T11:24:18.208195+00:00` |
| Raw hex received | `15303033` |
| ACK (06)? | `False` |
| NAK code | `003` |
| Result | **FAILED NAK 003 (Unrecognised command)** |

### Interpretation

- If ACK: queued OE/external data for Ethernet path was cleared.
- UI may show **Buffer empty** (or stay empty if already empty).
- Does not unload the template (`NOICE KM 200ML` should remain).

### Notes / user observation

**Follow-up research (NAK 003 on Step 14 — same code as Step 4):**

| Topic | Detail |
|-------|--------|
| Wire reply | `15303033` = NAK byte `15` + ASCII **`003`** |
| Manual (Part 8) | **`003 Unrecognised command code following <ESC>`** |
| Meaning | After `ESC` (`1B`), printer did **not recognise** the command ID bytes that followed |
| What followed ESC here | `}J1` = `7D 4A 31` (Codenet **2** double-byte command family starting with `}`) |
| What `}J` is supposed to do | Reset FIFO Data Buffer (Ethernet=`1`) — documented in Protocol manual |
| Same failure as | Step 4 `}D` (`1B7D443F04`) also got **NAK 003** |
| Pattern | **All `ESC } …` (`1B 7D …`) commands tried so far are rejected** on this unit |
| Likely cause | Firmware/build does not implement these Codenet-2 `}` commands (or pack not enabled) — not a wiring/IP error |
| Not the same as | NAK `020` “Command not implemented” — we specifically got **unrecognised ID** (`003`) |
| Working commands so far | Single-byte / `O*` family: `A`, `O1`, `1C`, `y`, `Q`, `[`, `T`, `ON`, `P` — all OK |
| Alternate FIFO clear | Use `OE` length `0000` (does **not** use `}`): e.g. clear TCP queue `1B4F45303030303004` |

User asked what NAK 003 is on Step 14 — documented above. User said **send 15**.

---

## Step 15 — Send FIFO / external field data (`OE`)

### Purpose

**Load variable text for the next print** into the printer’s external-data / FIFO buffer. The comma-separated values fill the updatable fields on template `NOICE KM 200ML` (the four `C` lines on the UI). Does **not** by itself fire a print — that is Step 16 `print_go` / photocell.

### Where
- **IP:** `192.168.1.40`
- **Port:** `7000`
- **Protocol:** Codenet over TCP
- **Transport:** Raw TCP socket `sendall` → `recv`

### How we send
1. Open TCP `192.168.1.40:7000`
2. Build `OE` frame: length (4 ASCII digits) + ASCII data
3. Send frame; read ACK/NAK
4. Close connection

### What we send

| Field | Value |
|-------|--------|
| Command | Send External FIFO Data `OE` |
| Data (ASCII) | `11/08/2026,10/05/2027,KFBNIKHIL7,158.00/0.79` |
| Data length | `44` → length field `0044` |
| ASCII meaning | `ESC` + `OE` + `0044` + data + `EOT` |
| Hex sent | `1B4F453030343431312F30382F323032362C31302F30352F323032372C4B46424E494B48494C372C3135382E30302F302E373904` |

### What we received

| Field | Value |
|-------|--------|
| Time (UTC) sent | `2026-08-13T11:27:02.137284+00:00` |
| Time (UTC) recv | `2026-08-13T11:27:02.253667+00:00` |
| Raw hex received | `06` |
| ACK (06)? | `True` |
| NAK code | `None` |
| Result | **FIFO data accepted (ACK) — buffer should show fields / not empty** |

### Interpretation

- ACK → one data record is queued for the **next** print.
- UI may leave **Buffer empty** and show field values instead of `C` placeholders (or still show preview depending on UI mode).
- Second `OE` without printing often NAKs on this site (FIFO ~1 deep).

### Notes / user observation

User said **send 16**.

---

## Step 16 — Print Go (`N`) — one print trigger

### Purpose

**Trigger one print**, same idea as a product-detect / photocell pulse. Uses the online template (`NOICE KM 200ML`) and the FIFO data loaded in Step 15 (if still in buffer). This can cause a **physical print**.

### Where
- **IP:** `192.168.1.40`
- **Port:** `7000`
- **Protocol:** Codenet over TCP
- **Transport:** Raw TCP socket `sendall` → `recv`

### How we send
1. Open TCP `192.168.1.40:7000`
2. Send Print Go for product detect `1`
3. Read ACK/NAK
4. Close connection

### What we send

| Field | Value |
|-------|--------|
| Command | Print Go `N` with product detect `1` |
| ASCII meaning | `ESC` + `N` + `1` + `EOT` |
| Hex sent | `1B4E3104` |
| Bytes | `0x1B 0x4E 0x31 0x04` |

### What we received

| Field | Value |
|-------|--------|
| Time (UTC) sent | `2026-08-13T11:30:21.033395+00:00` |
| Time (UTC) recv | `2026-08-13T11:30:21.077597+00:00` |
| Raw hex received | `06` |
| ACK (06)? | `True` |
| NAK code | `None` |
| Result | **Print Go accepted (ACK) — one print triggered like product detect** |

### Interpretation

- ACK → printer accepted the print-go command.
- Check UI / physical print for the Step 15 field values.
- FIFO may become empty after a successful print consume.

### Notes / user observation

*(waiting for user — describe what printed / UI buffer state. Planned probe sequence 1–16 complete.)*

---

## How to control Sequence off / Jet running / Phase locked

### UI (what you see)

Stop → **Select new state**:

| UI option | Meaning (Product Manual) |
|-----------|---------------------------|
| **Sequence off** | Jet stops; head flush; toward off/standby |
| **Jet running** | Jet keeps running; printing paused; no phasing / no deflector power |
| **Phase locked** | Jet running; printing paused; modulation+charging on; no deflector power |
| Pause printing (also in manual) | Jet running; printing paused; deflector power off |

Your panel also shows: **“Jet is on, but not printing”** with STATUS **Ready**.

### Codenet remote control (what the wire can do)

| Goal | Command | Hex | Notes |
|------|---------|-----|-------|
| **Sequence ON** → Ready to print | `OS 1` | `1B4F533104` | Like UI **Start** |
| **Sequence OFF** → Standby | `OS 0` | `1B4F533004` | Closest to UI **Sequence off** |
| **Query** jet sequence + status | `OS ?` | `1B4F533F04` | Returns state + jet status word |
| Soft pause print (jet may stay on) | `Q N` | `1B51314E04` | Inhibit printing (we tested) |
| Resume print | `Q Y` | `1B51315904` | We tested |

**Important:** Codenet **`OS` only SETs `0` or `1`** (off/on).  
There is **no documented SET** for exactly **“Jet running”** or **“Phase locked”** as Stop-menu targets. Those appear as **query status codes** when you read `OS ?`:

| Jet status (in `OS ?` reply) | Meaning |
|------------------------------|---------|
| `D307` | Ready to Print |
| `D807` | Jet Running |
| `DA07` | Phase Locked |
| `D207` | Printing Disabled |
| `E107` | Standby |
| `E307` | Fault |

So: **control** sequence with `OS 0`/`OS 1`; **observe** Jet running / Phase locked via `OS ?` (or UI). Fine stop modes (Jet running / Phase locked) are primarily **TouchPanel Stop menu**, not separate Codenet set commands in EPT033760.

### Practical mapping

| You want | Do this |
|----------|---------|
| Start printing capability (Ready) | UI Start **or** `OS 1` + `Q Y` + label online |
| Sequence off | UI **Sequence off** **or** `OS 0` |
| Pause prints, keep jet | `Q N` (and/or UI Pause / Jet running / Phase locked) |
| Resume prints | `Q Y` |
| See current jet sub-state | `OS ?` → decode status word |

### Caution

`OS 0` / `OS 1` change real jet sequencing (flush / startup time). Only send when you intend that — same as pressing Start/Stop on the panel.

---


| # | Command | Result |
|---|---------|--------|
| 1 | Identify `A?` | OK — identity reply |
| 2 | Status `O1?` | OK — Ready `001` |
| 3 | Status `1C?` | OK |
| 4 | Version `}D?` | NAK `003` unsupported |
| 5 | Liquids `y?` | OK — ink 007 / make-up 006 |
| 6 | Head `Q1?` | OK — `Y` enabled |
| 7 | Continuous `[?` | OK — OFF |
| 8 | Count T1 | OK — 304641327 |
| 9 | Count T2 | OK — 138 |
| 10 | `ON` NOICE KM 200ML | OK — ACK |
| 11 | Online `P1?` | OK — `P1NOI…` |
| 12 | Stop `Q1N` | OK — disabled |
| 13 | Resume `Q1Y` | OK — enabled |
| 14 | Clear FIFO `}J` | NAK `003` unsupported |
| 15 | FIFO `OE` | OK — ACK |
| 16 | Print Go `N` | **OK — ACK** |

---
