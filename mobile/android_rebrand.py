#!/usr/bin/env python3
"""Komboe Android rebrand (idempotent): applicationId io.komboe.android, app name Komboe, padlock-K launcher.
Kotlin namespace/package names stay upstream (internal identifiers); copyright/license text untouched.
GPL-3.0: the upstream LICENSE.txt and a corresponding-source notice are copied into the APK assets."""
import glob, os, re, shutil, sys

def install_android_kit(src, root):
    """Official navy/off-white launcher, notification, shield, authenticator wordmark, and autofill GIFs.

    Image replacement is not optional. require_pil() already aborted if Pillow is missing.
    """
    sys.path.insert(0, os.path.join(root, "scripts"))
    from komboe_brand import android_gif, android_vector_from_svg

    kit = os.path.join(root, "brand", "komboe-kit", "03-android", "res")
    if not os.path.isdir(kit):
        sys.exit(f"official Android kit missing: {kit}")
    for flavor_res in glob.glob(os.path.join(src, "app", "src", "*", "res")):
        for dirpath, _, files in os.walk(kit):
            for name in files:
                rel = os.path.relpath(os.path.join(dirpath, name), kit)
                if rel.startswith("values"):
                    # The kit colors file is only the mark palette. Copying it over
                    # app/src/main/res/values would duplicate ic_launcher_background.
                    continue
                dest = os.path.join(flavor_res, rel)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                shutil.copyfile(os.path.join(dirpath, name), dest)
                print("rebrand kit", os.path.relpath(dest, src))
        for color_file in glob.glob(os.path.join(flavor_res, "values", "ic_launcher_background.xml")):
            text = open(color_file, encoding="utf-8").read()
            updated = re.sub(
                r'(<color name="ic_launcher_background">)[^<]*<',
                r"\1#0B1B33<",
                text,
            )
            if updated != text:
                open(color_file, "w", encoding="utf-8").write(updated)
                print("rebrand launcher background", os.path.relpath(color_file, src))

    stat = os.path.join(kit, "drawable", "ic_stat_komboe.xml")
    foreground = os.path.join(kit, "drawable", "ic_launcher_foreground.xml")
    word = android_vector_from_svg(
        os.path.join(root, "brand", "komboe-kit", "05-wordmark-lockups", "komboe-lockup-horizontal-navy.svg"),
        "#0B1B33",
    )
    mark = android_vector_from_svg(
        os.path.join(root, "brand", "komboe-kit", "01-master", "komboe-mark-navy.svg"),
        "#0B1B33",
    )
    for path in glob.glob(os.path.join(src, "**", "res", "drawable*", "ic_notification*.xml"), recursive=True):
        shutil.copyfile(stat, path)
        print("rebrand notification", os.path.relpath(path, src))
    for path in glob.glob(os.path.join(src, "**", "res", "drawable*", "ic_shield*.xml"), recursive=True):
        shutil.copyfile(foreground, path)
        print("rebrand shield", os.path.relpath(path, src))
    for path in glob.glob(os.path.join(src, "**", "res", "drawable*", "logo_authenticator*.xml"), recursive=True):
        open(path, "w", encoding="utf-8").write(word)
        print("rebrand authenticator wordmark", os.path.relpath(path, src))
    for name, body in (
        ("logo_bitwarden.xml", word),
        ("logo_bitwarden_icon.xml", mark),
        ("logo_shield_icon.xml", mark),
    ):
        for path in glob.glob(os.path.join(src, "**", "res", "drawable*", name), recursive=True):
            png = os.path.join(os.path.dirname(os.path.dirname(path)), "drawable-nodpi", name[:-4] + ".png")
            if os.path.exists(png):
                os.remove(png)
            open(path, "w", encoding="utf-8").write(body)
            print("rebrand vector", os.path.relpath(path, src))
    for path in glob.glob(os.path.join(src, "**", "gif_setup_autofill.gif"), recursive=True):
        dark = "night" in path.replace("\\", "/")
        android_gif(path, dark=dark)
        print("rebrand gif", os.path.relpath(path, src))


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
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    from komboe_brand import require_pil
    require_pil()
    def rewrite_strings(t):
        from komboe_brand import rewrite_visible
        return "".join(
            l if re.search(r"copyright|licen[cs]e|not affiliated|corresponding source", l, re.I) else rewrite_visible(l)
            for l in t.splitlines(True)
        )
    for p in glob.glob(f"{S}/**/res/values*/strings*.xml", recursive=True):
        rw(p, rewrite_strings)
    for p in glob.glob(f"{S}/**/AndroidManifest.xml", recursive=True):
        rw(p, lambda t: t.replace('android:label="Bitwarden Bridge"', 'android:label="Komboe Bridge"'))
    for p in glob.glob(f"{S}/**/*.xml", recursive=True):
        if "targetPackage" not in open(p, encoding="utf-8", errors="ignore").read():
            continue
        rw(p, lambda t: t.replace('android:targetPackage="com.x8bit.bitwarden.dev"', 'android:targetPackage="io.komboe.android"')
           .replace('android:targetPackage="com.x8bit.bitwarden.beta"', 'android:targetPackage="io.komboe.android"')
           .replace('android:targetPackage="com.x8bit.bitwarden"', 'android:targetPackage="io.komboe.android"'))
    install_android_kit(S, ROOT)

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
