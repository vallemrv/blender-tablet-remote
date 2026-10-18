package com.blendertablet.remote.model

data class OutlinerTreeRow(
    val depth: Int,
    val collection: OutlinerCollection? = null,
    val obj: OutlinerObject? = null,
    val expanded: Boolean = false,
    val hasChildren: Boolean = false,
)

val OutlinerCollection.treeName: String get() = if (root) "/" else name

/** Repite las pertenencias compartidas en cada rama, sin confundir identidad y ruta. */
fun outlinerTreeRows(
    collections: List<OutlinerCollection>, objects: List<OutlinerObject> = emptyList(),
    collapsed: Set<String> = emptySet(), query: String = "",
): List<OutlinerTreeRow> {
    val search = query.trim()
    val children = collections.flatMap { c -> c.parents.map { it to c } }.groupBy({ it.first }, { it.second })
    val members = objects.flatMap { o -> o.collectionIds.map { it to o } }.groupBy({ it.first }, { it.second })
    val ids = collections.map { it.id }.toSet()
    fun visit(c: OutlinerCollection, depth: Int, ancestors: Set<String>, inheritedMatch: Boolean): List<OutlinerTreeRow> {
        if (c.id in ancestors) return emptyList()
        val matches = inheritedMatch || search.isEmpty() || c.treeName.contains(search, true)
        val descendants = children[c.id].orEmpty().sortedBy { it.name.lowercase() }
        val directObjects = members[c.id].orEmpty().sortedBy { it.name.lowercase() }
        val nested = descendants.flatMap { visit(it, depth + 1, ancestors + c.id, matches) } +
            directObjects.filter { matches || it.name.contains(search, true) }
                .map { OutlinerTreeRow(depth + 1, obj = it) }
        if (!matches && nested.isEmpty()) return emptyList()
        val expanded = search.isNotEmpty() || c.id !in collapsed
        return listOf(OutlinerTreeRow(depth, collection = c, expanded = expanded,
            hasChildren = descendants.isNotEmpty() || directObjects.isNotEmpty())) +
            if (expanded) nested else emptyList()
    }
    return collections.filter { it.root || it.parents.none(ids::contains) }
        .sortedWith(compareByDescending<OutlinerCollection> { it.root }.thenBy { it.name.lowercase() })
        .flatMap { visit(it, 0, emptySet(), false) } +
        objects.filter { it.collectionIds.none(ids::contains) && (search.isEmpty() || it.name.contains(search, true)) }
            .map { OutlinerTreeRow(0, obj = it) }
}
