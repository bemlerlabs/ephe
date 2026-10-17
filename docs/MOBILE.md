# Mobile

The same PWA on a phone, on the same local network. No app store, no build step.

## Phone Via QR

1. Start Ephe on your computer.
2. Open the desktop PWA.
3. Open **Settings → Mobile** (the panel is titled *Connect mobile*). Without LAN pairing running on
   the server, no code appears.
4. Scan the QR code with a phone on the same local network.
5. Chat from the mobile PWA while Ephe keeps running on your computer.

The QR flow is **LAN-first**. Public access is an optional online mode and must be selected explicitly.

## Mobile Pairing

If the phone cannot reach the computer, start Ephe with LAN binding:

```bash
ephe start --lan
```

The default QR code points to a LAN URL. Public access is available only through an explicit online
option and should be used only when you understand the exposure.
