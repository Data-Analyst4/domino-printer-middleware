# Domino Ax-Series Codenet Integration Notes

## Summary

The `Ax Series Codenet Protocol.pdf` describes Domino Ax150i, Ax350i, and Ax550i printers using Domino Codenet 2 protocol. This printer can be connected to a web app through middleware like the current Flask service, but it cannot use the current printer command path unchanged.

The current app sends compact JSON over TCP and expects JSON or semicolon-separated text replies. Domino Ax-Series Codenet expects raw byte commands framed with control characters:

- Start with `ESC` (`0x1B`).
- Follow with a command ID and command parameters.
- End with `EOT` (`0x04`).
- Positive response is `ACK` (`0x06`) or a framed query response.
- Negative response is `NAK` (`0x15`) followed by a 3 digit ASCII error code.

So the web app can still call an HTTP API, but the middleware must translate friendly JSON requests into Codenet byte packets before sending them to the Domino printer.

## How The Printer Communicates

### Supported Connection Types

The printer supports Codenet communication through:

- RS232 serial, if the printer has the RS232 connectivity pack.
- Ethernet TCP/IP, if the printer has the Basic Comms connectivity pack.

For a web app integration, Ethernet TCP/IP is the right path.

### Ethernet Setup

On the printer TouchPanel:

1. Go to `Home > Setup > Printer network > Advanced`.
2. Set `Protocol Setting` to `Codenet`.
3. Set `Protocol Mode` to `TCP`.
4. Set the `TCP Port`.
5. Enable the protocol.
6. Restart the printer after changing protocol settings.

The PDF says Ax-Series Codenet TCP ports available are:

- `7000`
- `7001`
- `7002`
- `7004`

The default port is `7000`.

The controller/middleware PC should have a fixed IP address in the same network range as the printer.

### Response Settings

The printer can be configured with two response-length modes:

- `Variable`: `ACK` is one byte (`06`), and `NAK` is four bytes (`15` + three ASCII error digits).
- `Fixed`: `ACK` and `NAK` are both four bytes. ACK is `06303030`, and NAK is `15` + three ASCII error digits.

It can also send responses at two times:

- `On Received`: ACK is sent as soon as the printer receives the packet. This does not mean the command was fully validated.
- `On Processed`: ACK/NAK is sent after the printer processes the command.

For middleware reliability, `On Processed` is safer because the API result reflects whether the printer accepted the command logic, not only whether bytes arrived.

## Codenet Command Format

Basic command:

```text
ESC CommandID Parameters EOT
```

Hex form:

```text
1B <command bytes> <parameter bytes> 04
```

Codenet 2 extended Ax-Series commands use a two-byte command ID starting with `}` (`0x7D`) or extended commands starting with `O` (`0x4F`).

Examples from the PDF:

- Printer identity query: `1B413F04`
- Get Codenet version: `1B7D443F04`
- Print Go using product detect 1: `1B4E3104`
- Put stored label slot `009` online: `1B503130303904`
- Store label `001` with data `ABC`: `1B5330303141424304`
- Download label without save to slot `001` with label data `ABCD`: `1B4F513030314142434404`
- Send external FIFO data `ABCD`: `1B4F45303030344142434404`
- Query current status: `1B31433F04`
- Extended current status query: `1B4F313F04`

## Main Printer Operations

### Identify Printer

Command `A` (`0x41`) asks the printer to return variant type. The manual recommends this as the first command to establish communication.

Request:

```text
1B413F04
```

The response is framed with `ESC A ... EOT` and includes printer type. Ax-Series printer type is `30`.

### Check Codenet Version

Command `}D` (`0x7D44`) gets the current Codenet version.

Request:

```text
1B7D443F04
```

### Query Status

Basic status request command `1` (`0x31`) supports current or historical status:

- Current status: `ESC 1 C ? EOT`
- Historical status: `ESC 1 H ? EOT`

Current status request:

```text
1B31433F04
```

Response contains a 3 digit status code, ink jet identifier, and status change time.

Extended status command `O1` (`0x4F31`) returns printer status and cabinet LED state:

```text
1B4F313F04
```

This is useful for dashboard integration.

### Put A Stored Label Online

If labels already exist in the printer store, command `P` (`0x50`) puts a 3 digit label slot online.

Example for label slot `009`:

```text
1B503130303904
```

### Trigger A Print

Command `N` (`0x4E`) initiates printing like a product detect signal.

Example for product detect `1`:

```text
1B4E3104
```

The printer should return ACK (`06`) or NAK with an error code.

### Store A Simple Label

Command `S` (`0x53`) stores a label using a 3 digit label name.

Example: store label `001` with text `ABC`:

```text
1B5330303141424304
```

### Store A Variable Name Label

Extended command `OM` (`0x4F4D`) stores a label with a variable length name.

Example from the PDF: label name `BEANS`, label data `ABCD`:

```text
1B4F4D30354245414E534142434404
```

### Retrieve Variable Name Label And Put Online

Extended command `ON` (`0x4F4E`) gets a named label from the label store and puts it online.

Example for label `BEANS`:

```text
1B4F4E3130354245414E5304
```

### Download Label Without Saving

Extended command `OQ` (`0x4F51`) downloads label data directly to the SGB without storing it in the label store.

Example: slot `001`, data `ABCD`:

```text
1B4F513030314142434404
```

This may be useful for dynamic web app printing, but the middleware must build proper label data and embedded formatting commands.

### Send External FIFO Data

Extended command `OE` (`0x4F45`) sends ASCII external data to the FIFO buffer for updatable text fields.

Example: send `ABCD`:

```text
1B4F45303030344142434404
```

The PDF also mentions another method: stream data to Ethernet port `16000` for external data. That is separate from Codenet command TCP ports.

## Error Handling

Positive acknowledgement:

```text
06
```

Negative acknowledgement:

```text
15 + 3 ASCII digits
```

Important NAK codes include:

- `002`: Invalid command header, ESC expected.
- `003`: Unrecognised command code after ESC.
- `004`: Unexpected characters before EOT.
- `005`: Invalid head selector.
- `007`: Command parameter out of permitted range.
- `008`: Print label number out of range.
- `009`: Syntax error.
- `010`: Print label too long for label store.
- `011`: Print label too long for print buffer.
- `012`: Invalid embedded format command.
- `016`: Cannot load label.
- `020`: Command not implemented.
- `024`: Checksum error.
- `027`: Command rejected, printing disabled.
- `050`: Printer is busy with auto repeat de-assert photocell.
- `051`: Internal printer error.
- `052`: Requested file could not be found.

The middleware should parse these NAK codes into readable API errors for the web app.

## Can It Connect Like The Current App?

Yes, at the architecture level:

```text
Web App -> HTTP API -> Middleware -> TCP Socket -> Domino Printer
```

But not at the protocol level. The current middleware sends JSON like:

```json
{"command":"STAR","templatename":"DEMO"}
```

The Domino Ax printer expects raw bytes like:

```text
1B413F04
```

Therefore the current app needs a printer-specific adapter.

## Required Middleware Changes

### Add Printer Protocol Types

Add a `protocol` field to printer config:

```json
{
  "DOMINO_AX_1": {
    "ip": "192.168.1.50",
    "port": 7000,
    "protocol": "domino_ax_codenet"
  },
  "P1": {
    "ip": "192.168.29.110",
    "port": 2030,
    "protocol": "json_tcp"
  }
}
```

### Add A Codenet Serializer

Create a module such as `app/services/domino_codenet_protocol.py` that can build byte payloads:

- `identity_query()` -> `1B413F04`
- `status_query()` -> `1B31433F04`
- `extended_status_query()` -> `1B4F313F04`
- `put_label_online(slot)` -> `1B5031<slot>04`
- `print_go(detector)` -> `1B4E<detector>04`
- `store_label(slot, label_data)` -> `1B53<slot><label_data>04`
- `download_label(slot, label_data)` -> `1B4F51<slot><label_data>04`
- `send_fifo_data(data)` -> `1B4F45<length><data>04`

### Add A Codenet Response Parser

The parser should recognize:

- `06` as success.
- `06303030` as fixed-length success.
- `15xxx` as NAK with error code.
- `1B ... 04` as a query response frame.
- Single print acknowledgement characters if print acknowledgement flags are enabled.

### Add A Binary TCP Send Path

The current `ConnectionManager` serializes commands with JSON. Domino Codenet needs binary bytes. The app should either:

- Add `send_bytes(payload)` to the existing connection manager, or
- Add a separate `DominoCodenetConnectionManager`.

The existing socket connection, timeout, retry, and status logic can be reused.

### Add Friendly HTTP Commands

The web app should not send raw hex for normal operations. It should send high-level JSON to the middleware:

```json
{
  "printer_id": "DOMINO_AX_1",
  "action": "print_label",
  "label_slot": "009",
  "trigger": true
}
```

The middleware would translate that into:

1. `P` command to put label slot `009` online.
2. `N` command to trigger print.

For dynamic labels:

```json
{
  "printer_id": "DOMINO_AX_1",
  "action": "download_and_print",
  "slot": "001",
  "label_data": "ABCD"
}
```

The middleware would translate that into:

1. `OQ` command to download label data without saving.
2. Optional status check.
3. `N` command to trigger print.

For variable data:

```json
{
  "printer_id": "DOMINO_AX_1",
  "action": "send_fifo_data",
  "data": "BATCH123"
}
```

The middleware would translate that into `OE`.

## Recommended First Implementation

Start with a small safe subset:

1. Add Domino protocol support beside the current JSON TCP support.
2. Implement identity query `A`.
3. Implement status query `O1`.
4. Implement put stored label online `P`.
5. Implement print trigger `N`.
6. Implement NAK error parsing.
7. Test with the real printer using port `7000`.

After that works, add:

1. Store label `S`.
2. Download label without save `OQ`.
3. FIFO data `OE`.
4. FIFO setup `OP`.
5. Dashboard status display using `O1`.

## Important Operational Notes

- Configure printer response mode to `On Processed` for reliable API results.
- Use response length `Variable` unless the factory standard requires fixed responses.
- Keep printer IPs allowlisted in middleware. Do not let arbitrary web clients choose TCP targets.
- Use a queue for print jobs if commands include multi-step sequences like select label, send data, and trigger print.
- Lock per printer connection so command sequences do not interleave.
- Treat Codenet payloads as bytes, not UTF-8 JSON.
- Confirm whether labels are stored on the printer, downloaded per print, or populated through FIFO data. That decision changes the API design.

## Final Assessment

The Domino Ax-Series printer can be integrated with the current web app pattern, but it needs a new protocol adapter. The web app should continue sending JSON to the middleware, while the middleware converts that JSON into Domino Codenet TCP byte commands and converts ACK/NAK/query responses back into JSON for the web app.

The easiest first factory use case is printing an already stored label: the middleware selects a label slot with command `P`, then triggers printing with command `N`. Dynamic label creation and variable data are possible, but require additional Codenet label formatting and FIFO support.
