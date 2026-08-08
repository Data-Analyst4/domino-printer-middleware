# Domino Ax-Series Functionality And Web App Command Guide

## Purpose

This guide explains how the Domino Ax-Series printer works from a network/application point of view, based on `Ax Series Codenet Protocol.pdf`.

It focuses on what you need for a factory web app or middleware service:

- How the printer receives commands over TCP/IP.
- What Codenet packets look like.
- What the printer can do through Codenet.
- How a network device or web app should send print commands.
- What middleware changes are needed in the current project.

## High Level Understanding

Domino Ax-Series printers are Continuous Ink Jet (CIJ) printers. The protocol in the PDF is `Codenet 2`, used by Ax-Series printers such as:

- Ax150i
- Ax350i
- Ax550i

The printer does not receive normal HTTP requests and does not understand JSON directly. It receives raw Codenet byte packets through a TCP socket or RS232 serial connection.

The correct architecture for a web app is:

```text
Browser/Web App
  -> HTTP/HTTPS JSON request
  -> Middleware API
  -> TCP socket
  -> Domino Ax printer Codenet bytes
```

The web app should stay simple and send JSON to the middleware. The middleware should translate that JSON into Domino Codenet bytes.

## Network Connection Options

### Ethernet TCP/IP

This is the recommended method for connecting from a web app or factory network device.

The printer must have the Basic Comms connectivity pack.

Printer setup path:

```text
Home > Setup > Printer network > Advanced
```

Required settings:

- `Protocol Setting`: `Codenet`
- `Protocol Mode`: `TCP`
- `Protocol Enabled`: enabled
- `TCP Port`: one of the supported Codenet ports

Available Ax-Series Codenet TCP ports:

- `7000`
- `7001`
- `7002`
- `7004`

Default port:

- `7000`

The middleware PC should use a stable/fixed IP address and be reachable from the printer network.

### RS232 Serial

This is also supported, but it is less suitable for a web app unless the middleware PC has a serial adapter connected to the printer.

Default RS232 settings from the PDF:

- COM port: `COM2`
- Baud rate: `9600`
- Data bits: `8`
- Parity: none
- Stop bits: `1`
- Flow control default: `RTS/CTS`

For the current web middleware project, TCP/IP is the practical choice.

## Codenet Packet Format

Every normal Codenet command starts with `ESC` and ends with `EOT`.

Control bytes:

- `ESC`: `0x1B`
- `EOT`: `0x04`
- `ACK`: `0x06`
- `NAK`: `0x15`
- Query character `?`: `0x3F`

Basic command shape:

```text
ESC CommandID Parameters EOT
```

Hex shape:

```text
1B <command id bytes> <parameter bytes> 04
```

Example: query printer identity:

```text
1B413F04
```

Meaning:

- `1B`: ESC
- `41`: command `A`
- `3F`: query `?`
- `04`: EOT

Important rule: when the printer sees `EOT` (`04`), it stops listening for that packet. Bytes after `EOT` are lost/ignored for that packet.

## Responses

### Positive Response

In variable response mode, success is:

```text
06
```

In fixed response mode, success is:

```text
06303030
```

That is ACK plus ASCII `000`.

### Negative Response

Failure is:

```text
15xxx
```

Where `xxx` is a 3 digit ASCII error code.

Example:

```text
15007
```

Meaning:

- `15`: NAK
- `007`: command parameter out of permitted range

### Query Response

Some commands return a full framed packet instead of just ACK.

Example response shape:

```text
ESC CommandID Data EOT
```

Example identity response:

```text
1B413330353630363036373031303004
```

The middleware must parse both simple ACK/NAK responses and framed query responses.

## Response Timing

The printer has a `Send Response` setting:

- `On Received`: ACK is sent as soon as bytes are received. This does not prove the command is valid.
- `On Processed`: ACK/NAK is sent after the printer processes the command.

For a web app, `On Processed` is strongly preferred because the API response should tell the caller whether the printer really accepted the operation.

## Command Families

Codenet commands are grouped into these main families:

- Initialisation commands: identify printer, read Codenet version, set clock.
- Print control commands: select labels, trigger printing, enable head, clear labels, product detector setup.
- Status commands: read current status, historical status, liquid levels.
- Global printer format commands: global label reverse, bold, print format, print height.
- Label formatting commands: embedded commands inside labels for fonts, serial numbers, clocks, barcodes, etc.
- Extended Codenet commands: FIFO data, variable name labels, download labels without saving, ink jet sequencing, extended status.

For integration with a web app, you normally start with print control, status, and selected extended commands.

## Important Commands For Web App Integration

### Printer Identity

Use this first to confirm that the device is responding and is a Domino/Ax-Series printer.

Command:

```text
A
```

Request:

```text
1B413F04
```

Expected response:

```text
ESC A <printer type and firmware info> EOT
```

Ax-Series printer type is `30`.

Web API action idea:

```json
{
  "printer_id": "DOMINO_AX_1",
  "action": "identify"
}
```

### Codenet Version

Command:

```text
}D
```

Request:

```text
1B7D443F04
```

Use this for diagnostics and startup checks.

### Extended Current Status

Command:

```text
O1
```

Request:

```text
1B4F313F04
```

Response contains:

- 3 digit status value.
- 2 digit LED state.

Useful statuses include:

- `000`: no alert
- `001`: ready
- `002`: sequencing on
- `003`: sequencing off
- `009`: standby
- `011`: fault
- `012`: initialising

LED states include:

- `00`: green on
- `02`: amber on
- `04`: red on
- `10`: green flashing
- `20`: amber flashing
- `40`: red flashing

This is the best command to power a web dashboard.

Web API action idea:

```json
{
  "printer_id": "DOMINO_AX_1",
  "action": "status"
}
```

### Basic Status Request

Command:

```text
1
```

Current status request:

```text
1B31433F04
```

Historical status request:

```text
1B31483F04
```

The printer stores the last 16 status change reports in a FIFO queue. Historical status returns the oldest buffered report and removes it.

### Read Liquid Levels

Command:

```text
y
```

Request:

```text
1B793F04
```

Response contains ink and make-up levels. The PDF says values are three digits, normally `000` to `008`; `021` means the sensor is unplugged.

This is useful for maintenance dashboards.

### Sequence Ink Jet On Or Off

Command:

```text
OS
```

Sequence off:

```text
1B4F533004
```

Sequence on:

```text
1B4F533104
```

Query:

```text
1B4F533F04
```

This command remotely sequences the ink jet on/off. It does not power the printer electrically. Use this carefully because it affects printer operating state.

Web app access to this should be admin-only.

## Label And Printing Workflows

The Domino printer can print in several different ways. The best choice depends on how your factory currently manages labels.

### Workflow 1: Print Existing Stored Label

This is the safest first integration.

The label already exists in the printer label store. The web app only selects a label and triggers printing.

Steps:

1. Query printer status with `O1`.
2. Put stored label online with `P`.
3. Trigger print with `N`.
4. Optionally query status again.

Command `P`: get label from store and put online.

Example: put label slot `009` online:

```text
1B503130303904
```

Command `N`: print go.

Example: trigger print using product detect `1`:

```text
1B4E3104
```

Recommended web request:

```json
{
  "printer_id": "DOMINO_AX_1",
  "action": "print_stored_label",
  "label_slot": "009",
  "product_detect": "1"
}
```

Middleware sequence:

```text
send P(label_slot=009)
wait ACK
send N(product_detect=1)
wait ACK
return final JSON result
```

This is the simplest way to connect the printer to the web app.

### Workflow 2: Download Label Without Saving

Use this when the web app generates a label dynamically and you do not want to store it permanently in the printer label store.

Command:

```text
OQ
```

Example: slot `001`, label data `ABCD`:

```text
1B4F513030314142434404
```

Recommended web request:

```json
{
  "printer_id": "DOMINO_AX_1",
  "action": "download_label_without_save",
  "slot": "001",
  "label_data": "ABCD"
}
```

To print after download:

```json
{
  "printer_id": "DOMINO_AX_1",
  "action": "download_and_print",
  "slot": "001",
  "label_data": "ABCD",
  "product_detect": "1"
}
```

Middleware sequence:

```text
send OQ(slot=001, label_data)
wait ACK
send N(product_detect=1)
wait ACK
```

Important: real `label_data` is not just plain product text if you need fonts, barcodes, clocks, multiple lines, serial numbers, or layout. It must include Codenet label formatting commands.

### Workflow 3: Store Label In Printer

Use this when the web app or admin tool creates/updates labels that should remain on the printer.

Command:

```text
S
```

Example: store label `001` with data `ABC`:

```text
1B5330303141424304
```

Recommended web request:

```json
{
  "printer_id": "DOMINO_AX_1",
  "action": "store_label",
  "label_slot": "001",
  "label_data": "ABC"
}
```

The printer overwrites the location if it is already occupied.

### Workflow 4: Store Label With Variable Length Name

Use this when labels are named by product code or product name instead of a numeric slot.

Command:

```text
OM
```

Example from the PDF: store label `BEANS` with data `ABCD`:

```text
1B4F4D30354245414E534142434404
```

Command `ON` retrieves a variable-name label and puts it online.

Example: put `BEANS` online:

```text
1B4F4E3130354245414E5304
```

Recommended web request:

```json
{
  "printer_id": "DOMINO_AX_1",
  "action": "print_named_label",
  "label_name": "BEANS",
  "product_detect": "1"
}
```

Middleware sequence:

```text
send ON(label_name=BEANS)
wait ACK
send N(product_detect=1)
wait ACK
```

### Workflow 5: Send Variable Data To FIFO

Use this when the label already contains updatable text fields, and each product needs changing data such as batch number, MRP, date, serial, carton ID, or QR content.

Command:

```text
OE
```

Example: send data `ABCD`:

```text
1B4F45303030344142434404
```

Meaning:

- `1B`: ESC
- `4F45`: command `OE`
- `30303034`: length `0004`
- `41424344`: data `ABCD`
- `04`: EOT

Recommended web request:

```json
{
  "printer_id": "DOMINO_AX_1",
  "action": "send_fifo_data",
  "data": "BATCH123"
}
```

The PDF says `OE` works with ASCII data. For Unicode, data must be streamed to the printer Ethernet data port instead.

### Workflow 6: Configure FIFO For External Data

Command:

```text
OP
```

This configures how external data is accepted:

- Start character, such as STX.
- End character, such as ETX.
- ASCII or Unicode encoding.
- Fixed data block length.
- ACK/NAK on received external data.
- Historic log setup.
- Duplicate packet handling.
- What to do when label changes.

This should be configured during printer setup or through an admin-only API.

## Network Device Integration

A PLC, scanner, industrial PC, or other network device can connect in two possible ways.

### Option A: Device Talks Directly To Printer

The device opens TCP connection to printer port `7000` and sends raw Codenet bytes.

This is fast, but every device must understand Codenet. It also makes logging, retry, security, and error reporting harder.

### Option B: Device Talks To Middleware

The device sends HTTP/JSON or another simple protocol to the middleware. The middleware converts it to Codenet.

This is better for maintainability:

- One place to implement Codenet.
- One place to log all print jobs.
- One place to parse NAK errors.
- Easier web dashboard.
- Easier security and printer allowlisting.
- Easier retry and queue logic.

Recommended factory architecture:

```text
Web App / PLC / Scanner / ERP
  -> Middleware API
  -> Domino Codenet TCP port 7000
  -> Printer
```

## Middleware Design For Current App

The current app has the right outer shape but the wrong printer protocol for Domino.

Current app:

```text
HTTP JSON -> compact JSON over TCP -> current printer
```

Domino required:

```text
HTTP JSON -> Codenet binary bytes over TCP -> Domino printer
```

Recommended additions:

- Add `protocol` to printer configuration.
- Add a Domino Codenet command builder.
- Add a Domino Codenet response parser.
- Add a binary TCP sender.
- Add high-level HTTP actions for Domino commands.
- Use a queue for multi-step print sequences.
- Add a per-printer lock so commands do not interleave.

Example config:

```json
{
  "DOMINO_AX_1": {
    "ip": "192.168.1.50",
    "port": 7000,
    "protocol": "domino_ax_codenet"
  }
}
```

Example response from middleware:

```json
{
  "success": true,
  "printer_id": "DOMINO_AX_1",
  "protocol": "domino_ax_codenet",
  "action": "print_stored_label",
  "steps": [
    {
      "command": "P",
      "hex": "1B503130303904",
      "ok": true,
      "response": "06"
    },
    {
      "command": "N",
      "hex": "1B4E3104",
      "ok": true,
      "response": "06"
    }
  ]
}
```

## Command Builder Rules

The middleware should not let frontend users send arbitrary hex by default. Instead it should expose safe actions and build hex internally.

Recommended safe command builders:

- `identify()` builds `1B413F04`.
- `get_codenet_version()` builds `1B7D443F04`.
- `get_status()` builds `1B4F313F04`.
- `get_basic_current_status()` builds `1B31433F04`.
- `read_liquid_levels()` builds `1B793F04`.
- `put_label_online(label_slot)` builds command `P`.
- `print_go(product_detect)` builds command `N`.
- `store_label(label_slot, label_data)` builds command `S`.
- `download_label(slot, label_data)` builds command `OQ`.
- `send_fifo_data(data)` builds command `OE`.
- `sequence_ink_jet(state)` builds command `OS`, admin-only.

Validation rules:

- Label slot must be `001` to `255`.
- Head select should be `1` for Ax-Series.
- Product detect should normally be `1` or `2`; for Ax-Series, both map similarly according to the PDF.
- FIFO `OE` data length must be `0001` to `1024`.
- Label names for `OM`/`ON` must be 1 to 50 allowed characters.
- Never send data after EOT.
- Encode command parameters as ASCII digits unless the command specifically uses binary values.

## Error Code Handling

The middleware should translate NAK codes into readable errors.

Important codes:

- `000`: software error.
- `002`: invalid command header, ESC expected.
- `003`: unrecognised command code following ESC.
- `004`: unexpected characters before EOT.
- `005`: invalid head selector.
- `007`: command parameter out of permitted range.
- `008`: print label number out of range.
- `009`: syntax error.
- `010`: print label too long for label store.
- `011`: print label too long for print buffer.
- `012`: invalid embedded format command.
- `013`: invalid character in print label.
- `016`: cannot load label.
- `017`: specified print label number is invalid.
- `020`: command not implemented.
- `024`: checksum error.
- `027`: command rejected, printing disabled.
- `050`: printer busy with auto repeat de-assert photocell.
- `051`: internal printer error.
- `052`: requested file could not be found.

Example API error:

```json
{
  "success": false,
  "error": "Command parameter out of permitted range",
  "nak_code": "007",
  "raw_response": "15007"
}
```

## Recommended First Factory Test Plan

1. Connect middleware PC and printer on the same network.
2. Enable Codenet TCP on printer port `7000`.
3. Set response timing to `On Processed`.
4. Send identity query `1B413F04`.
5. Send extended status query `1B4F313F04`.
6. Put an existing test label online with `P`.
7. Trigger a print with `N`.
8. Confirm ACK responses and physical print.
9. Test one invalid label slot to confirm NAK parsing.
10. Only after that, test dynamic label download or FIFO data.

## Recommended Web App Features

For operator users:

- Select product/label.
- Send print request.
- Show print accepted/failed.
- Show printer status.
- Show last error with readable message.

For admin or maintenance users:

- Identify printer.
- Query Codenet version.
- Query liquid levels.
- Query and show LED/status state.
- Sequence ink jet on/off.
- Store or update labels.
- Configure FIFO.

Avoid exposing raw hex commands in normal UI. Raw command sending should be restricted to developer/admin diagnostics only.

## Practical Recommendation

Start with stored label printing:

```text
Web app selects product -> middleware maps product to label slot -> middleware sends P -> middleware sends N
```

This keeps the printer label design inside the Domino printer and makes the web app integration small and reliable.

After stored label printing works, add FIFO variable data if your factory needs per-product values such as batch number, MRP, expiry date, carton ID, or barcode content.

Dynamic label generation from the web app is possible, but it is more complex because the middleware must generate Domino label formatting commands correctly.
