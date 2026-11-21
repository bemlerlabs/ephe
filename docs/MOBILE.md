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

## The Public Hop

Public pairing runs an `ssh` reverse tunnel from this machine to a tunnel endpoint, which forwards
the phone's requests back to the local server. Three bounds hold it.

**Explicit.** `mode=auto` never opens the hop. When the Wi-Fi address does not answer, the QR answer
carries the firewall diagnosis and `public_offer: true`; the Mobile panel turns that into one button,
*Open a public tunnel*, which asks again with `mode=public`. The address is readable by anyone who
holds it, and the panel says so in both languages instead of leaving that to a hint.

**Pinned.** The endpoint presents an SSH host key, and it is verified against
`utils/tunnel_known_hosts`, a file this repository owns and ships with the code. `~/.ssh/known_hosts`,
the system-wide store and any DNS answer are taken out of that decision on the command line, so an
earlier unverified connection or another program running as this user decides nothing. An unknown or
changed key ends the attempt: the panel names the refusal and the QR stays on the LAN URL. Nothing
here ever falls back to trusting.

**Bounded.** The hop closes on its own once no request has been admitted on its own address for
*Settings → Engine → Advanced → Discard an idle public tunnel (minutes)* — 30 minutes by default,
5 to 240. Traffic on `127.0.0.1` from the desktop is not a reason for a public address to keep
standing. While the hop runs, the pairing group says how long it has been up and how long until it
closes.

### Rotating a pinned key

A refusal that names the host key means the endpoint presented a key this file does not carry. That
is either a planned rotation or somebody sitting between this machine and the endpoint, and from here
the two look identical. Take the fingerprint ssh reported and compare it against both sources the
endpoint publishes for its key types — its published fingerprint table and the SHA-256 `SSHFP`
records signed in DNS for the host (`dig +dnssec SSHFP <host> <resolver>`) — over a channel that is
not the connection being verified. Only when they agree, add the key as a new line in
`utils/tunnel_known_hosts` and ship it. `tests/test_mobile_public_tunnel.py` pins the fingerprints the
file carries, so a rotation is a deliberate edit that a test follows. A key matching neither source is
an interception: leave the file alone and the tunnel stays refused, which is the answer it is for.
