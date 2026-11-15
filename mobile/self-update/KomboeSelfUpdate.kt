package io.komboe.android.update

import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageInstaller
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.widget.Toast
import java.io.File
import java.net.HttpURLConnection
import java.net.URI
import java.security.MessageDigest
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean
import com.x8bit.bitwarden.R

/**
 * In-app OTA for io.komboe.android. There is no Play Store and no USB after the first sideload.
 * The default feed is https://komboe.com/downloads/android/latest.json (override the string resource
 * komboe_update_feed_url at build time). APK bytes must be https on the same host, and sha256 must match.
 * Checks and downloads use whatever network has internet: Wi-Fi, mobile data, ethernet, or a VPN.
 * There is no Wi-Fi-only mode. The downloaded APK is installed with PackageInstaller, so Android
 * keeps the existing signing certificate.
 */
object KomboeSelfUpdate {
    const val ACTION_INSTALL_STATUS = "io.komboe.android.update.INSTALL_STATUS"
    /** Compiled into the APK so a strings scan can see the network policy. */
    const val NETWORK_POLICY = "wifi-or-mobile-data"
    private const val PERIOD_MS = 24L * 60 * 60 * 1000
    private const val CONNECT_TIMEOUT_MS = 20_000
    private const val READ_TIMEOUT_MS = 60_000
    private val io = Executors.newSingleThreadExecutor()
    private val main = Handler(Looper.getMainLooper())
    private val periodicArmed = AtomicBoolean(false)

    fun feedUrl(context: Context): String =
        context.getString(R.string.komboe_update_feed_url).trim()

    /** Check on this process start, then again every 24 hours while the process stays up. */
    fun schedulePeriodic(context: Context) {
        val app = context.applicationContext
        io.execute { runCheck(app, promptIfUpToDate = false) }
        if (periodicArmed.compareAndSet(false, true)) {
            main.postDelayed({
                periodicArmed.set(false)
                schedulePeriodic(app)
            }, PERIOD_MS)
        }
    }

    fun checkNow(context: Context) {
        val app = context.applicationContext
        toast(app, app.getString(R.string.komboe_update_checking))
        io.execute { runCheck(app, promptIfUpToDate = true) }
    }

    private fun runCheck(context: Context, promptIfUpToDate: Boolean) {
        try {
            if (!canDownload(context)) {
                toast(context, context.getString(R.string.komboe_update_need_network))
                return
            }
            val feed = feedUrl(context)
            require(feed.startsWith("https://", ignoreCase = true)) { "feed URL must be https" }
            val body = httpGet(feed)
            val manifest = KomboeSelfUpdateManifest.parse(body, feed)
            val installed = installedVersionCode(context)
            if (manifest.minSdk != null && Build.VERSION.SDK_INT < manifest.minSdk) {
                toast(context, context.getString(R.string.komboe_update_min_sdk, manifest.minSdk))
                return
            }
            if (manifest.versionCode <= installed) {
                if (promptIfUpToDate) {
                    toast(context, context.getString(R.string.komboe_update_current, installed.toString()))
                }
                return
            }
            toast(context, context.getString(R.string.komboe_update_downloading, manifest.versionName))
            val apk = downloadAndVerify(context, manifest)
            install(context, apk)
        } catch (error: Exception) {
            toast(context, error.message?.take(180) ?: context.getString(R.string.komboe_update_failed))
        }
    }

    private fun canDownload(context: Context): Boolean {
        val cm = context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val network = cm.activeNetwork ?: return false
        val caps = cm.getNetworkCapabilities(network) ?: return false
        if (!caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)) return false
        // Wi-Fi, mobile data, ethernet, and VPN. NETWORK_POLICY is referenced so the dex keeps it.
        val allowed = caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) ||
            caps.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR) ||
            caps.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET) ||
            caps.hasTransport(NetworkCapabilities.TRANSPORT_VPN)
        return allowed && NETWORK_POLICY == "wifi-or-mobile-data"
    }

    private fun installedVersionCode(context: Context): Long {
        val info = context.packageManager.getPackageInfo(context.packageName, 0)
        return if (Build.VERSION.SDK_INT >= 28) info.longVersionCode else @Suppress("DEPRECATION") info.versionCode.toLong()
    }

    private fun httpGet(url: String): String {
        val connection = open(url)
        try {
            val code = connection.responseCode
            require(code in 200..299) { "feed HTTP $code" }
            return connection.inputStream.bufferedReader().use { it.readText() }
        } finally {
            connection.disconnect()
        }
    }

    private fun downloadAndVerify(context: Context, manifest: KomboeSelfUpdateManifest): File {
        val target = File(context.cacheDir, "komboe-update.apk")
        if (target.exists()) target.delete()
        val connection = open(manifest.apkUrl)
        try {
            val code = connection.responseCode
            require(code in 200..299) { "apk HTTP $code" }
            val digest = MessageDigest.getInstance("SHA-256")
            connection.inputStream.use { input ->
                target.outputStream().use { output ->
                    val buffer = ByteArray(64 * 1024)
                    while (true) {
                        val read = input.read(buffer)
                        if (read <= 0) break
                        digest.update(buffer, 0, read)
                        output.write(buffer, 0, read)
                    }
                }
            }
            val actual = digest.digest().joinToString("") { "%02x".format(it) }
            if (actual != manifest.sha256) {
                target.delete()
                error("APK sha256 did not match the feed")
            }
            return target
        } finally {
            connection.disconnect()
        }
    }

    private fun open(url: String): HttpURLConnection {
        val parsed = URI(url).toURL()
        val connection = parsed.openConnection() as HttpURLConnection
        connection.instanceFollowRedirects = true
        connection.connectTimeout = CONNECT_TIMEOUT_MS
        connection.readTimeout = READ_TIMEOUT_MS
        connection.setRequestProperty("Accept", "*/*")
        connection.setRequestProperty("User-Agent", "Komboe-Android-SelfUpdate")
        return connection
    }

    private fun install(context: Context, apk: File) {
        val installer = context.packageManager.packageInstaller
        val params = PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL)
        params.setSize(apk.length())
        val sessionId = installer.createSession(params)
        installer.openSession(sessionId).use { session ->
            session.openWrite("apk", 0, apk.length()).use { out ->
                apk.inputStream().use { it.copyTo(out) }
                session.fsync(out)
            }
            val intent = Intent(context, KomboeSelfUpdateReceiver::class.java).setAction(ACTION_INSTALL_STATUS)
            val flags = PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_MUTABLE
            val pending = PendingIntent.getBroadcast(context, sessionId, intent, flags)
            session.commit(pending.intentSender)
        }
    }

    private fun toast(context: Context, message: String) {
        main.post { Toast.makeText(context, message, Toast.LENGTH_LONG).show() }
    }
}
