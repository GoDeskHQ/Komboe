#!/usr/bin/env python3
"""The branding check fails on the strings the 3d61fa1a audit still found."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("check_branding", ROOT / "scripts/check_branding.py")
check = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules["check_branding"] = check
spec.loader.exec_module(check)

spec = importlib.util.spec_from_file_location("komboe_brand", ROOT / "scripts/komboe_brand.py")
brand = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(brand)


OLD = [
    "On your computer open a browser and go to vault.bitwarden.com",
    "Learn more at www.bitwarden.com",
    "https://www.bitwarden.com/help",
    "شهادات النظام ليست آمنة مثل استيراد الشهادات إلى بت وردين",
    "സ്വയം ഹോസ്റ്റ് ചെയ്ത ബിറ്റ് വാർഡൻ പരിസ്ഥിതി",
    '<path fill="#6D4AFF" d="M192.19 20.75a.5.5 0 0 0-.37-.17"/>',
]


def must_fail(text: str) -> None:
    hits = check.visible_hits(text, "audit.txt")
    hits.extend(check.shield_hits(text.encode(), "audit.txt", ("M192.19 20.75a.5.5",)))
    if not hits:
        raise SystemExit(f"expected a branding hit for {text!r}")


def must_pass(text: str) -> None:
    hits = check.visible_hits(text, "audit.js")
    if hits:
        raise SystemExit(f"protocol host was flagged: {text!r} -> {hits}")


def main() -> None:
    for text in OLD:
        must_fail(text)
    must_pass('webVault: "https://vault.bitwarden.com"')
    must_pass('identity: "https://identity.bitwarden.com"')
    must_pass('api: "https://api.bitwarden.com"')
    must_pass('domain: "bitwarden.com"')
    rewritten = brand.rewrite_visible(
        "go to vault.bitwarden.com and www.bitwarden.com. بت وردين. ബിറ്റ് വാർഡൻ"
    )
    for banned in ("bitwarden.com", "بت وردين", "ബിറ്റ് വാർഡൻ"):
        if banned in rewritten:
            raise SystemExit(f"rewrite left {banned!r} in {rewritten!r}")
    if "komboe.com" not in rewritten or "Komboe" not in rewritten:
        raise SystemExit(f"rewrite did not insert Komboe: {rewritten!r}")
    kept = brand.rewrite_visible("https://api.bitwarden.com")
    if kept != "https://api.bitwarden.com":
        raise SystemExit(f"protocol host was rewritten: {kept!r}")
    print("BRANDING AUDIT PASS")


if __name__ == "__main__":
    main()
