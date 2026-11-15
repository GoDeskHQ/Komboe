# Android E2E harness (Phase B #83)

Komboe Android is built as `io.komboe.android` (fdroid debug) via `mobile/android-build.sh`.  
**This document does not claim a device/emulator run happened.** It records the harness and the exact steps to run when a device is available.

Updated 2026-11-05 Arizona MST.

## What exists today

| Piece | Path | Notes |
|---|---|---|
| Upstream pin | `mobile/ANDROID_UPSTREAM_PIN` | `v2026.10.1-bwpm` |
| Build | `mobile/android-build.sh` | Produces fdroid debug APK |
| Rebrand | `mobile/android_rebrand.py` | Komboe label, padlock-K assets, GPL assets |
| GPL SDK surface | `mobile/komboe-sdk` | Replaces `com.bitwarden:sdk-android` |
| Artifact check (no device) | `tests/features/phase_b.py` `#83` | Zip/manifest/badging only |
| Pre-device smoke | `mobile/android-e2e-check.sh` | APK presence, package id, label, GPL assets, biometric permission strings when APK present |
| Combined harness | `mobile/android-harness.sh` | Runs e2e-check then instrumentation; never claims device E2E |
| Device launch probe | `mobile/android-instrumentation.sh` | Optional adb install/launch; SKIP without device |

PIN / biometric unlock live in the upstream Android tree after clone+rebrand; they need a real device or emulator with a screen lock enrolled. iOS remains blocked without macOS.

## Pre-device check (safe on the build box)

```sh
# Prefer the combined harness (static + optional adb probe):
bash mobile/android-harness.sh
# or individually:
bash mobile/android-e2e-check.sh
bash mobile/android-instrumentation.sh
# optional:
KOMBOE_ARTIFACTS=/workspace/artifacts bash mobile/android-harness.sh
```

Exit 0 means docs/scripts (and the APK when present) look installable. When an APK is present, `android-e2e-check.sh` also looks for `USE_BIOMETRIC` / `USE_FINGERPRINT` permission strings in the binary manifest (packaging signal only). It does **not** mean login/autofill/PIN/biometric E2E passed.

## Device / emulator runbook (when hardware is available)

Prerequisites: Android SDK platform-tools (`adb`), an emulator AVD or a physical device with USB debugging, and the debug APK from `mobile/android-build.sh`.

```sh
# 1. Build (if needed)
bash mobile/android-build.sh
APK=${KOMBOE_ARTIFACTS:-/workspace/artifacts}/komboe-android-debug.apk
# or from the gradle output path printed by android-build.sh

# 2. Install
adb devices
adb install -r "$APK"

# 3. Launch
adb shell am start -n io.komboe.android/.MainActivity || \
  adb shell monkey -p io.komboe.android -c android.intent.category.LAUNCHER 1

# 4. Manual E2E checklist (record pass/fail; do not mark STATUS #83 done until these pass)
#    [ ] App label shows Komboe; splash uses padlock-K
#    [ ] Self-host server URL can be set
#    [ ] Register or log in against a local/test vault
#    [ ] Sync shows vault items
#    [ ] Autofill service can be enabled in Android settings
#    [ ] PIN unlock: set PIN in settings, lock vault, unlock with PIN
#    [ ] Biometric unlock: enroll device biometrics, enable in Komboe, lock, unlock
#    [ ] No Bitwarden Inc. user-facing branding in chrome/settings

# 5. Capture evidence
adb exec-out screencap -p > /tmp/komboe-android-e2e.png
adb logcat -d | rg -i 'komboe|AndroidRuntime' | tail -200 > /tmp/komboe-android-e2e.log
```

## Instrumentation hooks

### Pre-device (always safe)

```sh
bash mobile/android-e2e-check.sh
```

### Device launch probe (optional)

When `adb` sees a device/emulator:

```sh
bash mobile/android-instrumentation.sh
# optional:
KOMBOE_ANDROID_APK=/path/to/komboe-android-debug.apk bash mobile/android-instrumentation.sh
```

This installs (if APK present), launches `io.komboe.android`, and dumps the resumed activity. It does **not** mark STATUS #83 done.

### Future Espresso / Compose UI tests

When we add Espresso / Compose UI tests against the rebranded tree, keep them under the cloned android sources after rebrand (not committed upstream clones). Prefer:

- Package id assertions: `io.komboe.android`
- Login → vault list smoke against `KOMBOE_TLS_URL`
- Explicit `@Ignore("needs device biometrics")` on biometric cases so CI stays honest

Until those tests land, `android-e2e-check.sh` + `android-instrumentation.sh` + this checklist are the harness.

## In-app self-update

The fdroid debug (and release) APK built by `mobile/android-build.sh` includes Settings → About → Check for updates after `android_rebrand.py` runs. Desktop already used `KOMBOE_UPDATE_FEED`; Android uses `https://komboe.com/downloads/android/latest.json` (override `komboe_update_feed_url` at build time). This section does **not** claim a device run happened.

### Publish a feed entry

1. Build: `bash mobile/android-build.sh` and note the fdroid debug APK path.
2. Record `versionName`, `versionCode` (`aapt dump badging` or `dumpsys package io.komboe.android`), and `sha256sum` of the APK.
3. Host the APK and a `latest.json` like `distribution/android/latest.example.json` at an https origin. The default is `https://komboe.com/downloads/android/`. `apkUrl` must be https on that same host.
4. Until that host exists, point a debug build at a staging URL you already control by editing `mobile/self-update/komboe_update_strings.xml` before the build.

### Fold5 manual E2E (do not mark OTA done until these pass)

Use a build that already contains this feature. An older sideload cannot update itself until that first build is installed over USB once.

- [ ] Confirm “Restrict updates to Wi-Fi” is off (the default).
- [ ] On Wi-Fi, open Komboe → Settings → About.
- [ ] Confirm the current version row, then tap **Check for updates**.
- [ ] When the hosted `versionCode` is not newer: the app says it is up to date.
- [ ] Publish a higher `versionCode` on the feed. On mobile data, with the Wi-Fi-only toggle still off, start the app or tap **Check for updates**. The app downloads the APK, verifies sha256, and shows the system install prompt. Complete it. After upgrade, About shows the new version.
- [ ] Turn “Restrict updates to Wi-Fi” on, disable Wi-Fi, and tap **Check for updates**. The app refuses and tells you updates are set to Wi-Fi only.
- [ ] Turn the toggle off, stay on mobile data, and confirm a newer feed still installs.
- [ ] A bad sha256 in the feed must not install. A non-https `apkUrl` or a different host than the feed must be rejected.
- [ ] No Bitwarden Inc. branding in the new About rows.

A second USB sideload is still required once for phones that were installed before this build.
