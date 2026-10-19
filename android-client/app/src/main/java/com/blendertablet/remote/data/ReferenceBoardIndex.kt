package com.blendertablet.remote.data

import org.json.JSONArray
import org.json.JSONObject

data class ReferenceRecord(val id: String, val name: String)

/** Solo metadatos: las imágenes antiguas nunca se asignan a una escena por defecto. */
class ReferenceBoardIndex(boardsJson: String = "{}", legacyJson: String = "[]") {
    private val boards = runCatching { JSONObject(boardsJson) }.getOrDefault(JSONObject())
    private var legacy = runCatching { JSONArray(legacyJson) }.getOrDefault(JSONArray())
    private fun records(array: JSONArray?): List<ReferenceRecord> = (0 until (array?.length() ?: 0)).mapNotNull { index ->
        val item = array?.optJSONObject(index) ?: return@mapNotNull null
        val id = item.optString("id")
        if (!id.matches(Regex("[a-f0-9-]{36}"))) null else ReferenceRecord(id, item.optString("name", "Referencia"))
    }
    private fun array(items: List<ReferenceRecord>) = JSONArray().apply {
        items.forEach { put(JSONObject().put("id", it.id).put("name", it.name)) }
    }
    fun list(board: String) = if (board.isBlank()) emptyList() else records(boards.optJSONArray(board))
    fun previous() = records(legacy)
    fun add(board: String, image: ReferenceRecord) {
        require(board.isNotBlank())
        boards.put(board, array(list(board).filterNot { it.id == image.id } + image))
    }
    fun remove(board: String, id: String) { boards.put(board, array(list(board).filterNot { it.id == id })) }
    fun recover(board: String, id: String) {
        val image = previous().firstOrNull { it.id == id } ?: return
        add(board, image)
        legacy = array(previous().filterNot { it.id == id })
    }
    fun contains(id: String): Boolean = previous().any { it.id == id } ||
        boards.keys().asSequence().any { board -> list(board).any { it.id == id } }
    fun boardsJson(): String = boards.toString()
    fun legacyJson(): String = legacy.toString()
}
