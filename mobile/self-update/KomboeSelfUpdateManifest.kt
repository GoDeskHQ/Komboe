package io.komboe.android.update

import org.json.JSONObject
import java.net.URI

/**
 * HTTPS update feed for the Komboe Android app.
 *
 * Example:
 * {
 *   "versionName": "2026.11.1",
 *   "versionCode": 2026110101,
 *   "apkUrl": "https://komboe.com/downloads/android/io.komboe.android-2026.11.1.apk",
 *   "sha256": "0123...cdef",
 *   "minSdk": 29,
 *   "releaseNotes": "Updates install over Wi-Fi or mobile data."
 * }
 */
data class KomboeSelfUpdateManifest(
    val versionName: String,
    val versionCode: Long,
    val apkUrl: String,
    val sha256: String,
    val minSdk: Int?,
    val releaseNotes: String?,
) {
    companion object {
        fun parse(json: String, feedUrl: String): KomboeSelfUpdateManifest {
            val obj = JSONObject(json)
            val versionName = obj.getString("versionName").trim()
            require(versionName.isNotEmpty()) { "versionName is required" }
            val versionCode = obj.getLong("versionCode")
            require(versionCode > 0) { "versionCode must be a positive integer" }
            val apkUrl = obj.getString("apkUrl").trim()
            require(apkUrl.startsWith("https://", ignoreCase = true)) { "apkUrl must be https" }
            val sha256 = obj.getString("sha256").trim().lowercase()
            require(sha256.matches(Regex("^[0-9a-f]{64}$"))) { "sha256 must be 64 hex characters" }
            val minSdk = if (obj.has("minSdk") && !obj.isNull("minSdk")) obj.getInt("minSdk") else null
            if (minSdk != null) require(minSdk > 0) { "minSdk must be a positive integer" }
            val releaseNotes = obj.optString("releaseNotes").ifBlank { null }
            requireSameHost(feedUrl, apkUrl)
            return KomboeSelfUpdateManifest(
                versionName = versionName,
                versionCode = versionCode,
                apkUrl = apkUrl,
                sha256 = sha256,
                minSdk = minSdk,
                releaseNotes = releaseNotes,
            )
        }

        fun requireSameHost(feedUrl: String, apkUrl: String) {
            val feed = URI(feedUrl)
            val apk = URI(apkUrl)
            require(feed.scheme.equals("https", ignoreCase = true)) { "feed URL must be https" }
            require(apk.scheme.equals("https", ignoreCase = true)) { "apkUrl must be https" }
            val feedHost = feed.host?.lowercase() ?: error("feed URL host is missing")
            val apkHost = apk.host?.lowercase() ?: error("apkUrl host is missing")
            require(feedHost == apkHost) { "apkUrl host must match the feed host" }
        }
    }
}
