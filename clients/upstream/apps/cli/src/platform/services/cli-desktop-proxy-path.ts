import * as fs from "fs";
import * as os from "os";
import * as path from "path";

export const DESKTOP_PROXY_PATH_ENV = "KOMBOE_DESKTOP_PROXY_PATH";
const LEGACY_DESKTOP_PROXY_PATH_ENV = "BITWARDEN_DESKTOP_PROXY_PATH";

/** Returns well-known locations for the desktop native-messaging proxy. */
export function getDesktopProxyPaths(
  platform = os.platform(),
  homeDir = os.homedir(),
  environment: NodeJS.ProcessEnv = process.env,
): string[] {
  if (platform === "win32") {
    return [
      environment.LOCALAPPDATA &&
        path.win32.join(environment.LOCALAPPDATA, "Programs", "Komboe", "desktop_proxy.exe"),
      environment.ProgramFiles &&
        path.win32.join(environment.ProgramFiles, "Komboe", "desktop_proxy.exe"),
      environment["ProgramFiles(x86)"] &&
        path.win32.join(environment["ProgramFiles(x86)"], "Komboe", "desktop_proxy.exe"),
    ].filter((candidate): candidate is string => candidate != null);
  }

  if (platform === "darwin") {
    return [
      "/Applications/Komboe.app/Contents/MacOS/desktop_proxy",
      path.posix.join(homeDir, "Applications/Komboe.app/Contents/MacOS/desktop_proxy"),
    ];
  }

  return [
    "/opt/Komboe/desktop_proxy",
    "/usr/lib/komboe/desktop_proxy",
    "/snap/komboe/current/desktop_proxy",
  ];
}

/** Resolves an explicit override or the first installed desktop proxy. */
export function resolveDesktopProxyPath(
  proxyPaths = getDesktopProxyPaths(),
  override = process.env[DESKTOP_PROXY_PATH_ENV] || process.env[LEGACY_DESKTOP_PROXY_PATH_ENV],
  exists: (candidate: string) => boolean = fs.existsSync,
): string {
  if (override != null && override !== "") {
    if (!exists(override)) {
      throw new Error(
        `${DESKTOP_PROXY_PATH_ENV} points to a file that does not exist: ${override}`,
      );
    }
    return override;
  }

  const proxyPath = proxyPaths.find(exists);
  if (proxyPath == null) {
    throw new Error(
      `Could not find the Komboe Desktop proxy. Set ${DESKTOP_PROXY_PATH_ENV} to its path.`,
    );
  }
  return proxyPath;
}
