# Signing and privacy grants on macOS

Date: 2026-10-26. Order: S25 N1. Why a rebuild can lose the microphone grant,
which privacy keys the bundle declares, and what a stable signature changes.

## What the installed bundle said on 2026-10-26

```
$ codesign -dv /Applications/Ephe.app
Identifier=app-145d7b5368b17e38
Signature=adhoc
TeamIdentifier=not set
```

```
$ plutil -p /Applications/Ephe.app/Contents/Info.plist | grep Usage
(no output)
```

```
$ codesign -d -r- /Applications/Ephe.app
# designated => cdhash H"e0482c269ec9b78c3d20a3d02e65cc35982e966f"
```

The bundle identifier in the same file is `com.ephe.ephe`; the identifier the
ad-hoc signature carries is a synthesized one. macOS keys a privacy grant to the
code requirement, and an ad-hoc requirement is the build hash — so the next build
is a different app in the eyes of the system, and the grant does not follow.

The missing usage keys were the sharper defect: the composer calls
`getUserMedia({ audio: true })` (`app/src/components/dashboard/chat/useComposerVoiceInput.ts`),
and WebKit ends the host process when a page requests the microphone and the
bundle has no `NSMicrophoneUsageDescription`. `app/src-tauri/Info.plist` now
declares it together with the four folder and volume keys, and
`tests/test_macos_usage_strings.py` reads the source for every constraint the app
requests and refuses a bundle that declares fewer.

## Which grants Ephe can trigger

| Grant | Triggered by | Declared key |
|---|---|---|
| Microphone | the composer's voice button | `NSMicrophoneUsageDescription` |
| Desktop folder | a picked file that lives there | `NSDesktopFolderUsageDescription` |
| Documents folder | a picked file that lives there | `NSDocumentsFolderUsageDescription` |
| Downloads folder | a picked file that lives there | `NSDownloadsFolderUsageDescription` |
| External volume | a picked file on that volume | `NSRemovableVolumesUsageDescription` |
| Network volume | a picked file on that volume | `NSNetworkVolumesUsageDescription` |

Nothing here asks for the camera, screen recording, accessibility control or
Automation, so no key for those is declared. The app is not sandboxed, which is
why no `com.apple.security.*` entitlement is needed for a picked file or the
microphone; the TCC prompt is the whole gate.

## A stable identity

The build signs with whatever `APPLE_SIGNING_IDENTITY` names, or with Tauri's
configured `bundle.macOS.signingIdentity`; with neither, `cargo tauri build`
falls back to ad-hoc, which is the state measured above.

A self-signed certificate in the login keychain is enough for a local or source
build: create a `Code Signing` certificate whose common name is stable (for
example `Ephe Local Signing`), then build with that name. A Developer ID
Application certificate gives the same stability and is what a notarized build
needs; notarization remains optional and belongs to paid distribution.

```
APPLE_SIGNING_IDENTITY="Ephe Local Signing" npm run tauri build
```

The requirement then names the identifier and that certificate instead of a
build hash, and a rebuild keeps the same identity. Print it and compare the two
builds line by line:

```
codesign -d -r- path/to/Ephe.app
```

## The rebuild test

1. Build and install once, and grant the microphone from a real request.
2. Build again, replace only the `.app` (the updater does exactly that).
3. `codesign -dv` and `codesign -d -r-` must name the same identifier and the
   same certificate before and after, and the microphone must answer without a
   new prompt.

With an ad-hoc signature step 3 fails by construction; the honest interim answer
is to grant again after each rebuild.

## Repair path

`codesign -dv` names the identity, `codesign -d -r-` the designated
requirement, and `plutil -p <app>/Contents/Info.plist | grep Usage` the declared
keys. Running a reset removes the grant and the next request asks again — that
is the documented repair, not a permanent setting:

```
tccutil reset Microphone com.ephe.ephe
tccutil reset SystemPolicyDesktopFolder com.ephe.ephe
tccutil reset SystemPolicyDocumentsFolder com.ephe.ephe
tccutil reset SystemPolicyDownloadsFolder com.ephe.ephe
```

The same entries are visible in System Settings → Privacy & Security, where a
revoked grant can be re-enabled without a reset.
