#!/usr/bin/env python3
"""Desktop updates itself from komboe.com by default and signs in to komboe.com by default."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    updater = (ROOT / "clients/upstream/apps/desktop/src/main/updater.main.ts").read_text()
    cli = (ROOT / "clients/upstream/apps/cli/src/commands/update.command.ts").read_text()
    admin = (ROOT / "server/upstream/src/api/admin.rs").read_text()

    assert 'process.env.KOMBOE_UPDATE_FEED === "0"' in updater
    assert 'process.env.KOMBOE_UPDATE_FEED !== "1"' not in updater
    env = (ROOT / "clients/upstream/libs/common/src/platform/services/default-environment.service.ts").read_text()
    assert 'KOMBOE_DEFAULT_BASE_URL = "https://komboe.com"' in env
    assert "return new SelfHostedEnvironment(komboeDefaultUrls());" in env
    assert "KOMBOE_UPDATE_URL" in updater
    assert "await autoUpdater.checkForUpdates()" in updater
    assert "await autoUpdater.downloadUpdate()" in updater
    assert "autoUpdater.quitAndInstall(true, true)" in updater

    assert "KOMBOE_CLI_RELEASES_URL" in cli
    assert "A new version is available" in cli
    assert "You can download this update at" in cli

    assert "fn diagnostics" in admin
    assert "latest_release" in admin
    assert "admin_external_checks" in admin
    print("SELF UPDATE PASS")


if __name__ == "__main__":
    main()
