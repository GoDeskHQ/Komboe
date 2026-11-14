#!/usr/bin/env python3
"""Komboe Android rebrand (idempotent): applicationId io.komboe.android, app name Komboe, padlock-K launcher.
Kotlin namespace/package names stay upstream (internal identifiers); copyright/license text untouched.
GPL-3.0: the upstream LICENSE.txt and a corresponding-source notice are copied into the APK assets."""
import glob, os, re, shutil, sys

def main(src):
    global S, ROOT
    S = src
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    def rw(p, fn):
        t = open(p, encoding="utf-8").read(); n = fn(t)
        if n != t: open(p, "w", encoding="utf-8").write(n); print("rebrand", os.path.relpath(p, S))
    rw(f"{S}/app/build.gradle.kts", lambda t: t.replace('applicationId = "com.x8bit.bitwarden"', 'applicationId = "io.komboe.android"')
       .replace('archivesName.set("com.x8bit.bitwarden")', 'archivesName.set("io.komboe.android")')
       .replace('            applicationIdSuffix = ".dev"\n', ''))
    for p in glob.glob(f"{S}/app/src/*/res/values/strings_non_localized.xml"):
        rw(p, lambda t: re.sub(r'(name="app_name"[^>]*>)(?:Bitwarden|Komboe)( Beta| Dev)?<', r"\1Komboe<", t))
    for p in glob.glob(f"{S}/app/src/main/res/values*/strings.xml"):
        rw(p, lambda t: "".join(l if re.search(r"copyright|licen[cs]e|bitwarden\.com|@", l, re.I) else re.sub(r"\bBitwarden\b", "Komboe", l) for l in t.splitlines(True)))
    try:
        from PIL import Image
        src = Image.open(f"{ROOT}/branding/logo/master/komboe-logo-master-transparent.png").convert("RGBA")
        for p in glob.glob(f"{S}/app/src/*/res/mipmap-*/*.png") + glob.glob(f"{S}/app/src/*/res/mipmap-*/*.webp"):
            im = Image.open(p); size = im.size; c = Image.new("RGBA", size, (255, 255, 255, 255))
            l = src.copy(); l.thumbnail((int(size[0]*.8), int(size[1]*.8))); c.paste(l, ((size[0]-l.width)//2, (size[1]-l.height)//2), l)
            c.save(p)
    except ImportError: pass
    # Phase D: adaptive launcher icon (mipmap-anydpi overrides the PNG mipmaps on API 26+) and in-app logos -> padlock-K.
    # Compose painterResource only accepts vectors or rasters, so the vector XMLs are replaced by same-named PNGs (drawable-nodpi).
    try:
        from PIL import Image
        src = Image.open(f"{ROOT}/branding/logo/master/komboe-logo-master-transparent.png").convert("RGBA")
        def put(xml, size, frac, mono=False):
            d = os.path.join(os.path.dirname(os.path.dirname(xml)), "drawable-nodpi"); os.makedirs(d, exist_ok=True)
            c = Image.new("RGBA", (size, size), (0, 0, 0, 0)); l = src.copy(); l.thumbnail((int(size*frac),) * 2)
            if mono: l = Image.merge("RGBA", (*[Image.new("L", l.size, 255)] * 3, l.getchannel("A")))
            c.paste(l, ((size-l.width)//2, (size-l.height)//2), l)
            c.save(os.path.join(d, os.path.basename(xml)[:-4] + ".png")); os.remove(xml); print("rebrand icon", os.path.relpath(xml, S))
        for x in glob.glob(f"{S}/app/src/*/res/drawable/ic_launcher_foreground.xml"): put(x, 432, .55)
        for x in glob.glob(f"{S}/app/src/*/res/drawable/ic_launcher_monochrome.xml"): put(x, 432, .55, mono=True)
        # Phase E: in-app logos must stay VectorDrawables (screens load them with rememberVectorPainter): wordmark / mark as vector paths.
        import sys; sys.path.insert(0, f"{ROOT}/branding/wordmark"); from wordmark_lib import android_vector
        for n, wm, hdp, pad in [("logo_bitwarden", True, 34, 0), ("logo_shield_icon", False, 288, 1.0), ("logo_bitwarden_icon", False, 48, 0)]:
            xml = f"{S}/ui/src/main/res/drawable/{n}.xml"; png_ = f"{S}/ui/src/main/res/drawable-nodpi/{n}.png"
            if os.path.exists(png_): os.remove(png_)
            new = android_vector(hdp, "#6D4AFF", wordmark=wm, pad=pad)
            if not os.path.exists(xml) or open(xml).read() != new: open(xml, "w").write(new); print("rebrand vector", os.path.relpath(xml, S))
        for p in glob.glob(f"{S}/app/src/*/res/values/ic_launcher_background.xml"):
            rw(p, lambda t: re.sub(r"(<color name=\"ic_launcher_background\">)[^<]*<", r"\1#FFFFFF<", t))
    except ImportError: pass

    # GPL-3.0 §4–§6: the binary must carry the license text and say where the source is.
    assets = os.path.join(S, "app", "src", "main", "assets")
    os.makedirs(assets, exist_ok=True)
    upstream_license = os.path.join(S, "LICENSE.txt")
    if not os.path.isfile(upstream_license):
        sys.exit("Bitwarden Android LICENSE.txt is missing; refusing to build without the GPL text")
    license_head = open(upstream_license, encoding="utf-8").read(80)
    if "GNU GENERAL PUBLIC LICENSE" not in license_head:
        sys.exit("Upstream LICENSE.txt is not the GNU GPL text")
    shutil.copyfile(upstream_license, os.path.join(assets, "LICENSE.txt"))
    shutil.copyfile(os.path.join(ROOT, "mobile", "ANDROID-SOURCE.txt"), os.path.join(assets, "komboe-source.txt"))
    shutil.copyfile(os.path.join(ROOT, "THIRD-PARTY-NOTICES.md"), os.path.join(assets, "THIRD-PARTY-NOTICES.md"))
    print("rebrand gpl assets", "LICENSE.txt", "komboe-source.txt", "THIRD-PARTY-NOTICES.md")

    def patch(path, old, new, label):
        file = os.path.join(S, path)
        text = open(file, encoding="utf-8").read()
        if old not in text:
            if new in text:
                return
            sys.exit(f"gpl sdk wire: pattern missing in {path} ({label})")
        open(file, "w", encoding="utf-8").write(text.replace(old, new))
        print("gpl sdk", label)

    sdk_dir = os.path.join(ROOT, "mobile", "komboe-sdk")
    settings_path = os.path.join(S, "settings.gradle.kts")
    settings = open(settings_path, encoding="utf-8").read()
    if ":komboe-sdk" not in settings:
        open(settings_path, "a", encoding="utf-8").write(
            '\ninclude(":komboe-sdk")\nproject(":komboe-sdk").projectDir = file("%s")\n' % sdk_dir
        )
        print("gpl sdk", "settings")
    patch("build.gradle.kts", "lockMode.set(LockMode.STRICT)", "lockMode.set(LockMode.LENIENT)", "lock lenient")
    patch("app/build.gradle.kts", "    implementation(libs.bitwarden.sdk)\n", '    implementation(project(":komboe-sdk"))\n', "app dependency")
    patch("authenticator/build.gradle.kts", "    implementation(libs.bitwarden.sdk)\n", '    implementation(project(":komboe-sdk"))\n', "authenticator dependency")
    sdk_maven = '''        maven {
            name = "GitHubPackages (Bitwarden)"
            url = uri("https://maven.pkg.github.com/bitwarden/sdk")
            credentials {
                username = ""
                password = userProperties["gitHubToken"] as String? ?: System.getenv("GITHUB_TOKEN")
            }
        }
'''
    patch("settings.gradle.kts", sdk_maven, "", "drop sdk maven repo")
    patch(
        "app/src/main/kotlin/com/x8bit/bitwarden/data/platform/manager/SdkClientManagerImpl.kt",
        '''        if (!isBuildVersionAtLeast(Build.VERSION_CODES.S)) {
            nativeLibraryManager.loadLibrary("bitwarden_uniffi")
        }
''',
        "        // Komboe vault crypto is pure JVM code. There is no bitwarden_uniffi library to load.\n",
        "skip native sdk",
    )
    inject_self_update(S, ROOT)



def patch_tree(src, path, old, new, label):
    file = os.path.join(src, path)
    text = open(file, encoding="utf-8").read()
    if old not in text:
        if new in text:
            return
        sys.exit(f"gpl sdk wire: pattern missing in {path} ({label})")
    open(file, "w", encoding="utf-8").write(text.replace(old, new))
    print("gpl sdk", label)


def inject_self_update(src, root):
    """Copy the Komboe Wi-Fi OTA sources into the pinned Android tree and hook Settings → About."""
    dest_kt = os.path.join(src, "app/src/main/kotlin/io/komboe/android/update")
    os.makedirs(dest_kt, exist_ok=True)
    overlay = os.path.join(root, "mobile/self-update")
    for name in ("KomboeSelfUpdate.kt", "KomboeSelfUpdateManifest.kt", "KomboeSelfUpdateReceiver.kt"):
        shutil.copyfile(os.path.join(overlay, name), os.path.join(dest_kt, name))
        print("self-update", name)
    strings_dest = os.path.join(src, "app/src/main/res/values/komboe_update_strings.xml")
    os.makedirs(os.path.dirname(strings_dest), exist_ok=True)
    shutil.copyfile(os.path.join(overlay, "komboe_update_strings.xml"), strings_dest)
    print("self-update", "komboe_update_strings.xml")

    patch_tree(
        src,
        "app/src/main/AndroidManifest.xml",
        '    <uses-permission android:name="android.permission.INTERNET" />\n',
        '    <uses-permission android:name="android.permission.INTERNET" />\n'
        '    <uses-permission android:name="android.permission.REQUEST_INSTALL_PACKAGES" />\n',
        "install packages permission",
    )
    receiver = '''        <receiver
            android:name="io.komboe.android.update.KomboeSelfUpdateReceiver"
            android:exported="false">
            <intent-filter>
                <action android:name="io.komboe.android.update.INSTALL_STATUS" />
            </intent-filter>
        </receiver>
'''
    patch_tree(
        src,
        "app/src/main/AndroidManifest.xml",
        '        tools:targetApi="36">\n        <activity\n',
        '        tools:targetApi="36">\n' + receiver + '        <activity\n',
        "install status receiver",
    )
    patch_tree(
        src,
        "app/src/main/kotlin/com/x8bit/bitwarden/BitwardenApplication.kt",
        "        restrictionManager.initialize()\n        environmentRepository.initialize()\n",
        "        restrictionManager.initialize()\n        environmentRepository.initialize()\n"
        "        io.komboe.android.update.KomboeSelfUpdate.schedulePeriodic(this)\n",
        "periodic update check",
    )
    patch_tree(
        src,
        "app/src/main/kotlin/com/x8bit/bitwarden/ui/platform/feature/settings/about/AboutScreen.kt",
        "import androidx.compose.ui.Alignment\n",
        "import androidx.compose.ui.Alignment\nimport androidx.compose.ui.platform.LocalContext\n",
        "about LocalContext import",
    )
    about_hook = '''        val updateContext = LocalContext.current
        BitwardenTextRow(
            text = stringResource(id = com.x8bit.bitwarden.R.string.komboe_check_for_updates),
            onClick = { io.komboe.android.update.KomboeSelfUpdate.checkNow(updateContext) },
            withDivider = false,
            cardStyle = CardStyle.Middle(),
            modifier = Modifier
                .standardHorizontalMargin()
                .fillMaxWidth()
                .testTag(tag = "KomboeCheckForUpdatesRow"),
        )
        BitwardenSwitch(
            label = stringResource(id = com.x8bit.bitwarden.R.string.komboe_updates_wifi_only),
            contentDescription = stringResource(id = com.x8bit.bitwarden.R.string.komboe_updates_wifi_only),
            isChecked = io.komboe.android.update.KomboeSelfUpdate.wifiOnly(updateContext),
            onCheckedChange = { io.komboe.android.update.KomboeSelfUpdate.setWifiOnly(updateContext, it) },
            cardStyle = CardStyle.Middle(),
            modifier = Modifier
                .standardHorizontalMargin()
                .fillMaxWidth()
                .testTag(tag = "KomboeUpdatesWifiOnlyRow"),
        )
        CopyRow(
'''
    patch_tree(
        src,
        "app/src/main/kotlin/com/x8bit/bitwarden/ui/platform/feature/settings/about/AboutScreen.kt",
        "        CopyRow(\n",
        about_hook,
        "about check-for-updates row",
    )


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: android_rebrand.py /path/to/bitwarden-android")
    main(sys.argv[1])
