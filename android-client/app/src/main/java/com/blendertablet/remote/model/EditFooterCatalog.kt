package com.blendertablet.remote.model

object EditFooterCatalog {
    fun id(action: EditFooterAction): String? = when (action) {
        EditFooterAction.MAKE_EDGE_FACE -> "MAKE_EDGE_FACE"
        EditFooterAction.CONNECT_VERTICES -> "CONNECT_VERTICES"
        EditFooterAction.SEPARATE -> "SEPARATE"
        EditFooterAction.SPLIT -> "SPLIT"
        EditFooterAction.NORMALS_OUTSIDE -> "RECALCULATE_NORMALS_OUTSIDE"
        EditFooterAction.NORMALS_INSIDE -> "RECALCULATE_NORMALS_INSIDE"
        EditFooterAction.NORMALS_FLIP -> "FLIP_NORMALS"
        EditFooterAction.KNIFE, EditFooterAction.NORMALS -> null
    }
    val ids = EditFooterAction.entries.mapNotNull(::id).toSet()
}
