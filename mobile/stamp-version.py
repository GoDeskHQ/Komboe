#!/usr/bin/env python3
"""Stamp appVersionCode / appVersionName in gradle/libs.versions.toml."""
import pathlib
import re
import sys

def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit("usage: stamp-version.py <android-src> <versionCode> <versionName>")
    root, code, name = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
    path = root / "gradle" / "libs.versions.toml"
    text = path.read_text(encoding="utf-8")
    text2 = re.sub(r'appVersionCode\s*=\s*"[^"]*"', f'appVersionCode = "{code}"', text)
    text2 = re.sub(r'appVersionName\s*=\s*"[^"]*"', f'appVersionName = "{name}"', text2)
    if text2 == text:
        raise SystemExit(f"did not find appVersionCode/Name in {path}")
    path.write_text(text2, encoding="utf-8")
    print("version", name, code)

if __name__ == "__main__":
    main()
