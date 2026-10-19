package com.blendertablet.remote.data

import android.content.Context
import android.content.SharedPreferences
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.ImageDecoder
import android.net.Uri
import android.os.Build
import android.provider.OpenableColumns
import java.io.File
import java.util.UUID

data class ReferenceImage(val id: String, val name: String, val path: String)

/** Private, bounded copies keep references available after the source is moved. */
class ReferenceImages(context: Context) {
    companion object { private val metadataLock = Any() }
    private val resolver = context.contentResolver
    private val directory = File(context.filesDir, "references").apply { mkdirs() }
    private val preferences = context.getSharedPreferences("reference_images", Context.MODE_PRIVATE)

    private fun index() = ReferenceBoardIndex(preferences.getString("boards", "{}") ?: "{}",
        preferences.getString("images", "[]") ?: "[]")

    private fun images(records: List<ReferenceRecord>): List<ReferenceImage> = records.mapNotNull { item ->
        val file = File(directory, "${item.id}.png")
        if (file.isFile) ReferenceImage(item.id, item.name, file.path) else null
    }
    fun list(board: String): List<ReferenceImage> = images(index().list(board))
    fun previous(): List<ReferenceImage> = images(index().previous())

    /** Una importación terminada actualiza solo el tablero al que pertenecía al iniciarse. */
    fun observe(onChanged: () -> Unit): () -> Unit {
        val listener = SharedPreferences.OnSharedPreferenceChangeListener { _, key ->
            if (key == "boards" || key == "images") onChanged()
        }
        preferences.registerOnSharedPreferenceChangeListener(listener)
        onChanged()
        return { preferences.unregisterOnSharedPreferenceChangeListener(listener) }
    }
    private fun save(index: ReferenceBoardIndex) {
        check(preferences.edit().putString("boards", index.boardsJson()).putString("images", index.legacyJson()).commit()) {
            "No se pudo guardar el tablero de referencias"
        }
    }
    fun recover(board: String, image: ReferenceImage) = synchronized(metadataLock) {
        val index = index(); index.recover(board, image.id); save(index)
    }

    fun import(uri: Uri, board: String): ReferenceImage {
        require(board.isNotBlank()) { "Espera a recibir la escena" }
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
                val options = BitmapFactory.Options().apply { inSampleSize = 1 }
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
            synchronized(metadataLock) {
                val index = index(); index.add(board, ReferenceRecord(image.id, image.name)); save(index)
            }
            return image
        } catch (error: Exception) {
            destination.delete()
            throw error
        } finally { source.delete() }
    }

    fun remove(board: String, image: ReferenceImage) {
        synchronized(metadataLock) {
            val index = index(); index.remove(board, image.id); save(index)
            if (!index.contains(image.id)) File(directory, "${image.id}.png").delete()
        }
    }
}
