package com.blendertablet.remote.data

import android.content.Context
import android.content.SharedPreferences
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.ImageDecoder
import android.net.Uri
import android.os.Build
import android.provider.OpenableColumns
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.UUID

data class ReferenceImage(val id: String, val name: String, val path: String)

/** Private, bounded copies keep references available after the source is moved. */
class ReferenceImages(context: Context) {
    companion object { private val metadataLock = Any() }
    private val resolver = context.contentResolver
    private val directory = File(context.filesDir, "references").apply { mkdirs() }
    private val preferences = context.getSharedPreferences("reference_images", Context.MODE_PRIVATE)

    fun list(): List<ReferenceImage> = runCatching {
        val array = JSONArray(preferences.getString("images", "[]"))
        (0 until array.length()).mapNotNull { index ->
            val item = array.getJSONObject(index)
            val id = item.getString("id")
            if (!id.matches(Regex("[a-f0-9-]{36}"))) return@mapNotNull null
            val file = File(directory, "$id.png")
            if (file.isFile) ReferenceImage(id, item.getString("name"), file.path) else null
        }
    }.getOrDefault(emptyList())

    /** A finished import can outlive its Activity; reconcile the currently visible board. */
    fun observe(onChanged: (List<ReferenceImage>) -> Unit): () -> Unit {
        val listener = SharedPreferences.OnSharedPreferenceChangeListener { _, key ->
            if (key == "images") onChanged(list())
        }
        preferences.registerOnSharedPreferenceChangeListener(listener)
        onChanged(list())
        return { preferences.unregisterOnSharedPreferenceChangeListener(listener) }
    }

    private fun save(images: List<ReferenceImage>) {
        val array = JSONArray()
        images.forEach { array.put(JSONObject().put("id", it.id).put("name", it.name)) }
        check(preferences.edit().putString("images", array.toString()).commit()) {
            "No se pudo guardar la lista de referencias"
        }
    }

    fun import(uri: Uri): ReferenceImage {
        val id = UUID.randomUUID().toString()
        val source = File(directory, "$id.import")
        val destination = File(directory, "$id.png")
        try {
            resolver.openInputStream(uri)?.use { input ->
                source.outputStream().use { output ->
                    val buffer = ByteArray(8192)
                    var total = 0L
                    while (true) {
                        val count = input.read(buffer)
                        if (count < 0) break
                        total += count
                        require(total <= 32L * 1024 * 1024) { "La imagen supera 32 MB" }
                        output.write(buffer, 0, count)
                    }
                }
            } ?: error("No se puede abrir la imagen")
            val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
            BitmapFactory.decodeFile(source.path, bounds)
            require(bounds.outWidth > 0 && bounds.outHeight > 0) { "Formato de imagen no compatible" }
            val bitmap = if (Build.VERSION.SDK_INT >= 28) {
                ImageDecoder.decodeBitmap(ImageDecoder.createSource(source)) { decoder, info, _ ->
                    val ratio = minOf(1.0, 2048.0 / maxOf(info.size.width, info.size.height))
                    decoder.setTargetSize(maxOf(1, (info.size.width * ratio).toInt()), maxOf(1, (info.size.height * ratio).toInt()))
                    decoder.allocator = ImageDecoder.ALLOCATOR_SOFTWARE
                }
            } else {
                val options = BitmapFactory.Options()
                while (maxOf(bounds.outWidth, bounds.outHeight) / options.inSampleSize > 2048) options.inSampleSize *= 2
                BitmapFactory.decodeFile(source.path, options) ?: error("No se puede decodificar la imagen")
            }
            try {
                destination.outputStream().use { check(bitmap.compress(Bitmap.CompressFormat.PNG, 100, it)) }
            } finally { bitmap.recycle() }
            val name = runCatching {
                resolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { cursor ->
                    if (cursor.moveToFirst()) cursor.getString(0) else null
                }
            }.getOrNull()?.take(100) ?: "Referencia"
            val image = ReferenceImage(id, name, destination.path)
            synchronized(metadataLock) { save(list() + image) }
            return image
        } catch (error: Exception) {
            destination.delete()
            throw error
        } finally { source.delete() }
    }

    fun remove(image: ReferenceImage) {
        synchronized(metadataLock) { save(list().filterNot { it.id == image.id }) }
        File(directory, "${image.id}.png").delete()
    }
}
