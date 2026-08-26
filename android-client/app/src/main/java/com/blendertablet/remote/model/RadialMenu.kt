package com.blendertablet.remote.model

/**
 * Qué hay bajo el dedo cuando se abre el menú radial.
 *
 * Lo resuelve el servidor con `snap.query`, que lanza un rayo **sin tocar la
 * selección**: preguntar qué hay debajo no debe seleccionarlo, o el menú cambiaría
 * la escena antes de que el usuario elija nada.
 */
data class TouchContext(
    val mode: BlenderMode = BlenderMode.OBJECT,
    val selectionMode: SelectionMode = SelectionMode.VERTEX,
    /** El rayo dio con geometría. `false` = se pulsó el vacío. */
    val hit: Boolean = false,
    /** Objeto bajo el dedo, cuando el rayo acertó. */
    val objectName: String? = null,
    /** Ese objeto ya está seleccionado: cambia por completo qué se ofrece. */
    val objectSelected: Boolean = false,
    /** Hay algo seleccionado en el submodo activo (para Loop/Ring, Merge, etc.). */
    val hasSelection: Boolean = false,
)

/**
 * Resultado de sondear qué hay bajo el dedo (`snap.query`).
 *
 * [hit] a false significa "se pulsó el vacío", que es un contexto tan válido como
 * cualquier otro; `null` en vez de un [TouchProbe] significa "todavía no ha
 * contestado el servidor".
 */
data class TouchProbe(
    val hit: Boolean,
    val objectName: String? = null,
    val elementId: String? = null,
)

/**
 * Qué acciones ofrece la pulsación larga.
 *
 * El menú responde a **qué hay bajo el dedo**, no solo al modo global: tocar un
 * objeto que no está seleccionado ofrece seleccionarlo, y tocar el vacío ofrece
 * añadir objetos y operaciones de conjunto.
 *
 * En Object Mode estas acciones se pintan como menú contextual flotante
 * ([com.blendertablet.remote.ui.ContextSheet]) y en Edit como anillo radial;
 * esta clase es la fuente única en ambos casos.
 *
 * Es una función pura a propósito: así [com.blendertablet.remote.model.SurfaceCatalog]
 * puede comprobarse contra ella y el test falla si alguien cuela aquí una acción cuyo
 * propietario es el rail, el top o el footer. El long click no es un segundo rail.
 */
object RadialMenu {

    /** Tope del anillo: pasadas ~8 entradas los sectores se vuelven inpulsables. */
    const val MAX_ACTIONS = 8

    fun actionsFor(context: TouchContext): List<ActionId> {
        val actions = if (context.mode == BlenderMode.EDIT) editActions(context) else objectActions(context)
        return actions.take(MAX_ACTIONS)
    }

    private fun objectActions(context: TouchContext): List<ActionId> = buildList {
        when {
            // Sobre un objeto ajeno a la selección: primero engancharlo. Nada de
            // operarlo todavía; casi todos los comandos actúan sobre la selección y
            // tocarían otra cosa distinta de la que se está señalando.
            context.hit && !context.objectSelected -> {
                add(ActionId.SELECT_UNDER)
                add(ActionId.SELECT_ADD_UNDER)
                add(ActionId.RENAME)
            }
            // Sobre lo ya seleccionado: operaciones cortas sobre eso mismo.
            context.hit -> {
                add(ActionId.DUPLICATE_LINKED)
                add(ActionId.RENAME)
                add(ActionId.SELECT_ALL)
                add(ActionId.DESELECT_ALL)
                add(ActionId.HIDE_OBJECT)
                add(ActionId.APPLY_TRANSFORMS)
                add(ActionId.SET_ORIGIN)
            }
            // En el vacío no hay nada sobre lo que operar: añadir y operaciones de
            // conjunto. Agregar va primero porque es lo que más pide un tap al hueco;
            // Caja y Círculo arman el arrastre por forma para seleccionar varios.
            else -> {
                add(ActionId.ADD_OBJECT)
                add(ActionId.TOOL_BOX)
                add(ActionId.TOOL_CIRCLE)
                add(ActionId.SELECT_ALL)
                add(ActionId.DESELECT_ALL)
            }
        }
        // Borrar solo si hay algo que borrar, y siempre el último: es el destructivo.
        if (context.objectSelected || (!context.hit && context.hasSelection)) add(ActionId.DELETE)
    }

    private fun editActions(context: TouchContext): List<ActionId> = buildList {
        // Caja y Círculo arman el arrastre por forma: selección pura, va primero.
        // SELECT_INVERT salió del anillo para no pasarse del tope de 8 en aristas.
        add(ActionId.TOOL_BOX)
        add(ActionId.TOOL_CIRCLE)
        add(ActionId.SELECT_ALL)

        // Loop y Ring necesitan una arista de partida: sin ella el servidor
        // responde `empty_selection`, así que no se ofrecen.
        if (context.selectionMode == SelectionMode.EDGE && context.hasSelection) {
            add(ActionId.SELECT_LOOP)
            add(ActionId.SELECT_RING)
        }
        if (context.selectionMode == SelectionMode.FACE && context.hasSelection) {
            add(ActionId.DISSOLVE)
        }

        if (context.mode == BlenderMode.OBJECT) {
            if (context.hasSelection || context.hit) add(ActionId.HIDE_OBJECT)
        } else {
            if (context.hasSelection) add(ActionId.HIDE_GEOMETRY)
            add(ActionId.REVEAL_GEOMETRY)
        }
        if (context.hasSelection) add(ActionId.DELETE)
    }
}
