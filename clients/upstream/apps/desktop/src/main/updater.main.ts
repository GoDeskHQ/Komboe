import { app, dialog, IpcMainEvent, ipcMain, Notification } from "electron";
import log from "electron-log";
import { autoUpdater, UpdateDownloadedEvent, VerifyUpdateSupport } from "electron-updater";

import { I18nService } from "@bitwarden/common/platform/abstractions/i18n.service";
import { UrlType } from "@bitwarden/common/platform/misc/safe-urls";
import { LogService } from "@bitwarden/logging";

import { SafeShell } from "../platform/main/safe-shell.main";
import { isDev } from "../utils";

import { isMacAppStore, isWindowsPortable, isWindowsStore } from "./platform-utils.main";
import { WindowMain } from "./window.main";

const UpdaterCheckInitialDelay = 5 * 1000; // 5 seconds
const UpdaterCheckInterval = 12 * 60 * 60 * 1000; // 12 hours

const MaxTimeBeforeBlockingUpdateNotification = 7 * 24 * 60 * 60 * 1000; // 7 days

function versionIsNewer(remote: string, local: string): boolean {
  const parse = (value: string) => value.split(".").map((part) => parseInt(part, 10) || 0);
  const left = parse(remote);
  const right = parse(local);
  const length = Math.max(left.length, right.length);
  for (let index = 0; index < length; index++) {
    const a = left[index] ?? 0;
    const b = right[index] ?? 0;
    if (a !== b) {
      return a > b;
    }
  }
  return false;
}

export class UpdaterMain {
  private doingUpdateCheck = false;
  private doingUpdateCheckWithFeedback = false;
  private canUpdate = false;
  private linuxAppImage = false;
  private linuxDebPackage = false;
  private updateDownloaded: UpdateDownloadedEvent | null = null;
  private originalRolloutFunction: VerifyUpdateSupport | null = null;

  // This needs to be tracked to avoid the Notification being garbage collected,
  // which would break the click handler.
  private openedNotification: Notification | null = null;

  // This is used to set when the initial update notification was shown.
  // The system notifications can be easy to miss or be disabled, so we want to
  // ensure the user is eventually made aware of the update. If the user does not
  // interact with the notification in a reasonable time, we will prompt them again.
  private initialUpdateNotificationTime: number | null = null;

  constructor(
    private i18nService: I18nService,
    private logService: LogService,
    private windowMain: WindowMain,
    private shell: SafeShell,
  ) {
    autoUpdater.logger = log;

    // The build-time feed is komboe.com/downloads/desktop. KOMBOE_UPDATE_URL
    // replaces it with a generic https feed the operator hosts. Checks are on
    // by default; KOMBOE_UPDATE_FEED=0 or ELECTRON_NO_UPDATER=1 turns them off.
    const updateUrl = process.env.KOMBOE_UPDATE_URL;
    if (updateUrl != null && updateUrl.startsWith("https://")) {
      autoUpdater.setFeedURL({
        provider: "generic",
        url: updateUrl,
      });
    }
    // The shell stays on the constructor so startup wiring is unchanged.
    // Update checks do not open a browser.
    void this.shell;

    this.originalRolloutFunction = autoUpdater.isUserWithinRollout;

    // The AppImage replaces itself from https://komboe.com/downloads/desktop/latest-linux.yml
    // on any connection. The .deb cannot replace itself without root, so it prompts for the
    // AppImage, which is the self-updating Linux build. macOS has no CI build and no
    // latest-mac.yml, so it is left out of this feed.
    this.linuxAppImage = process.platform === "linux" && Boolean(process.env.APPIMAGE);
    this.linuxDebPackage = process.platform === "linux" && !this.linuxAppImage;
    const windowsCanUpdate =
      process.platform === "win32" && !isWindowsStore() && !isWindowsPortable();
    const macCanUpdate = process.platform === "darwin" && !isMacAppStore();
    this.canUpdate =
      !this.userDisabledUpdates() && (this.linuxAppImage || windowsCanUpdate || macCanUpdate);
  }

  async init() {
    global.setTimeout(async () => await this.checkForUpdate(), UpdaterCheckInitialDelay);
    global.setInterval(async () => await this.checkForUpdate(), UpdaterCheckInterval);

    autoUpdater.on("checking-for-update", () => {
      this.doingUpdateCheck = true;
    });

    autoUpdater.on("update-available", async () => {
      this.initialUpdateNotificationTime ??= Date.now();

      if (this.doingUpdateCheckWithFeedback) {
        if (this.windowMain.win == null) {
          this.reset();
          return;
        }

        const result = await dialog.showMessageBox(this.windowMain.win, {
          type: "info",
          title: this.i18nService.t("bitwarden") + " - " + this.i18nService.t("updateAvailable"),
          message: this.i18nService.t("updateAvailable"),
          detail: this.i18nService.t("updateAvailableDesc"),
          buttons: [this.i18nService.t("yes"), this.i18nService.t("no")],
          cancelId: 1,
          defaultId: 0,
          noLink: true,
        });

        if (result.response === 0) {
          await autoUpdater.downloadUpdate();
        } else {
          this.reset();
        }
      }
    });

    autoUpdater.on("update-not-available", async () => {
      if (this.doingUpdateCheckWithFeedback && this.windowMain.win != null) {
        await dialog.showMessageBox(this.windowMain.win, {
          message: this.i18nService.t("noUpdatesAvailable"),
          buttons: [this.i18nService.t("ok")],
          defaultId: 0,
          noLink: true,
        });
      }

      this.reset();
    });

    autoUpdater.on("update-downloaded", async (info) => {
      if (this.windowMain.win == null) {
        return;
      }

      this.updateDownloaded = info;
      await this.promptRestartUpdate(info, this.doingUpdateCheckWithFeedback);
    });

    autoUpdater.on("error", (error) => {
      if (this.doingUpdateCheckWithFeedback) {
        dialog.showErrorBox(
          this.i18nService.t("updateError"),
          error == null ? this.i18nService.t("unknown") : (error.stack || error).toString(),
        );
      }

      this.reset();
    });
  }

  async checkForUpdate(withFeedback = false) {
    if (isDev()) {
      return;
    }

    if (this.updateDownloaded && withFeedback) {
      await this.promptRestartUpdate(this.updateDownloaded, true);
      return;
    }

    if (this.doingUpdateCheck) {
      return;
    }

    if (this.linuxDebPackage && !this.userDisabledUpdates()) {
      await this.promptLinuxDebTowardAppImage(withFeedback);
      return;
    }

    if (!this.canUpdate) {
      if (withFeedback && this.windowMain.win != null) {
        await dialog.showMessageBox(this.windowMain.win, {
          type: "info",
          message:
            "Update checks are off because KOMBOE_UPDATE_FEED=0 or ELECTRON_NO_UPDATER=1 is set.",
          buttons: [this.i18nService.t("ok")],
          defaultId: 0,
          noLink: true,
        });
      }

      return;
    }

    this.doingUpdateCheckWithFeedback = withFeedback;
    if (withFeedback) {
      autoUpdater.autoDownload = false;

      // If the user has explicitly checked for updates, we want to bypass
      // the current staging rollout percentage
      autoUpdater.isUserWithinRollout = (info) => true;
    }

    await autoUpdater.checkForUpdates();
  }

  private reset() {
    autoUpdater.autoDownload = true;
    // Reset the rollout check to the default behavior
    if (this.originalRolloutFunction != null) {
      autoUpdater.isUserWithinRollout = this.originalRolloutFunction;
    }
    this.doingUpdateCheck = false;
    this.updateDownloaded = null;
  }

  private async promptRestartUpdate(info: UpdateDownloadedEvent, blocking: boolean) {
    // If we have an initial notification, and it's from a long time ago,
    // we will block the user with a dialog to ensure they see it.
    const longTimeSinceInitialNotification =
      this.initialUpdateNotificationTime != null &&
      Date.now() - this.initialUpdateNotificationTime > MaxTimeBeforeBlockingUpdateNotification;

    if (!longTimeSinceInitialNotification && !blocking && Notification.isSupported()) {
      // If the prompt doesn't have to block and we support notifications,
      // we will show a notification instead of a blocking dialog, which won't steal focus.
      await this.promptRestartUpdateUsingSystemNotification(info);
    } else {
      // If we are blocking, or notifications are not supported, we will show a blocking dialog.
      // This will steal the user's focus, so we should only do this for user initiated actions
      // or when there are no other options.
      await this.promptRestartUpdateUsingDialog(info);
    }
  }

  private async promptRestartUpdateUsingSystemNotification(info: UpdateDownloadedEvent) {
    if (this.openedNotification != null) {
      this.openedNotification.close();
    }

    this.openedNotification = new Notification({
      title: this.i18nService.t("bitwarden") + " - " + this.i18nService.t("restartToUpdate"),
      body: this.i18nService.t("restartToUpdateDesc", info.version),
      timeoutType: "never",
      silent: false,
    });

    // If the user clicks the notification, prompt again to restart, this time with a blocking dialog.
    this.openedNotification.on("click", () => {
      void this.promptRestartUpdate(info, true);
    });
    // If the notification fails to show, fall back to the blocking dialog as well.
    this.openedNotification.on("failed", (error) => {
      this.logService.error("Update notification failed", error);
      void this.promptRestartUpdate(info, true);
    });
    this.openedNotification.show();
  }

  private async promptRestartUpdateUsingDialog(info: UpdateDownloadedEvent) {
    const result = await dialog.showMessageBox(this.windowMain.win, {
      type: "info",
      title: this.i18nService.t("bitwarden") + " - " + this.i18nService.t("restartToUpdate"),
      message: this.i18nService.t("restartToUpdate"),
      detail: this.i18nService.t("restartToUpdateDesc", info.version),
      buttons: [this.i18nService.t("restart"), this.i18nService.t("later")],
      cancelId: 1,
      defaultId: 0,
      noLink: true,
    });

    if (result.response === 0) {
      if (!(await this.confirmUpdateRestart())) {
        this.reset();
        return;
      }

      // Quit and install have a different window logic, setting `isQuitting` just to be safe.
      this.windowMain.isQuitting = true;
      autoUpdater.quitAndInstall(true, true);
    } else {
      this.reset();
    }
  }

  /**
   * Asks the renderer to check for unsaved changes and prompt the user if needed.
   * Returns true if safe to restart, false if the user chose to stay.
   */
  private confirmUpdateRestart(): Promise<boolean> {
    if (this.windowMain.win == null) {
      return Promise.resolve(true);
    }

    return new Promise<boolean>((resolve) => {
      const timer = setTimeout(() => {
        ipcMain.removeListener("confirmUpdateRestart", handler);
        resolve(true);
      }, 30_000);

      const handler = (_: IpcMainEvent, canRestart: boolean) => {
        clearTimeout(timer);
        resolve(canRestart);
      };

      ipcMain.once("confirmUpdateRestart", handler);
      this.windowMain.win.webContents.send("confirmUpdateRestart");
    });
  }

  /**
   * The .deb install stays on the package the user installed. A newer feed version
   * opens the downloads page for the AppImage, which updates itself.
   */
  private async promptLinuxDebTowardAppImage(withFeedback: boolean) {
    const local = app.getVersion();
    let remote = "";
    try {
      remote = await this.linuxFeedVersion();
    } catch (error) {
      this.logService.error("Linux update feed failed", error);
      if (withFeedback && this.windowMain.win != null) {
        await dialog.showMessageBox(this.windowMain.win, {
          type: "error",
          message: "Komboe could not read the Linux update feed.",
          buttons: [this.i18nService.t("ok")],
          defaultId: 0,
          noLink: true,
        });
      }
      return;
    }
    const newer = versionIsNewer(remote, local);
    if (!newer && !withFeedback) {
      return;
    }
    if (this.windowMain.win == null) {
      return;
    }
    const detail = newer
      ? `Version ${remote} is available. This .deb does not replace itself. The AppImage is the Linux build that updates itself from komboe.com over any connection.`
      : "This .deb does not replace itself. The AppImage is the Linux build that updates itself from komboe.com over any connection.";
    const result = await dialog.showMessageBox(this.windowMain.win, {
      type: "info",
      title: "Komboe",
      message: newer ? "A Komboe update is available" : "Linux updates use the AppImage",
      detail,
      buttons: ["Open downloads", this.i18nService.t("later")],
      cancelId: 1,
      defaultId: 0,
      noLink: true,
    });
    if (result.response === 0) {
      this.shell.openExternal("https://komboe.com/downloads", UrlType.WebUrl);
    }
  }

  private async linuxFeedVersion(): Promise<string> {
    const base = (process.env.KOMBOE_UPDATE_URL ?? "https://komboe.com/downloads/desktop").replace(
      /\/$/,
      "",
    );
    const response = await fetch(`${base}/latest-linux.yml`);
    if (!response.ok) {
      throw new Error(`Linux update feed returned ${response.status}`);
    }
    const text = await response.text();
    const match = /^version:\s*(\S+)/m.exec(text);
    if (match == null) {
      throw new Error("Linux update feed has no version");
    }
    return match[1];
  }

  private userDisabledUpdates(): boolean {
    // Desktop checks komboe.com/downloads/desktop (or KOMBOE_UPDATE_URL) and
    // updates itself, like the Android app. KOMBOE_UPDATE_FEED=0 opts out.
    if (process.env.KOMBOE_UPDATE_FEED === "0") {
      return true;
    }
    for (const arg of process.argv) {
      if (arg != null && arg.toUpperCase().indexOf("--ELECTRON_NO_UPDATER=1") > -1) {
        return true;
      }
      if (arg != null && arg.toUpperCase().indexOf("--BITWARDEN_NO_UPDATER=1") > -1) {
        return true;
      }
    }
    return process.env.ELECTRON_NO_UPDATER === "1" || process.env.BITWARDEN_NO_UPDATER === "1";
  }
}
