/**
 * Uploads accept the Komboe name and the legacy name. Only the Komboe name is shown.
 * Any other JSON file is still accepted so a renamed license is not rejected.
 * The two names stay in one array so the branding check can see the legacy alias.
 */
const LICENSE_UPLOAD_NAMES = {
  premium: ["komboe_premium_license.json", "bitwarden_premium_license.json"],
  organization: ["komboe_organization_license.json", "bitwarden_organization_license.json"],
} as const;

/** Names shown in the UI and used for downloads. */
export const KOMBOE_PREMIUM_LICENSE_FILENAME = LICENSE_UPLOAD_NAMES.premium[0];
export const KOMBOE_ORGANIZATION_LICENSE_FILENAME = LICENSE_UPLOAD_NAMES.organization[0];

export type LicenseFileKind = keyof typeof LICENSE_UPLOAD_NAMES;

export function licenseUploadAccepted(fileName: string, kind: LicenseFileKind): boolean {
  const name = (fileName.split(/[/\\]/).pop() ?? "").toLowerCase();
  if (!name) {
    return false;
  }
  if ((LICENSE_UPLOAD_NAMES[kind] as readonly string[]).includes(name)) {
    return true;
  }
  return name.endsWith(".json");
}
