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
    /** El servidor anuncia `object.shade`; servidores antiguos no ven el toggle. */
    val objectShadingAvailable: Boolean = false,
    /** El objeto activo ya está suave: el interruptor ofrecerá volver a plano. */
    val shadeSmooth: Boolean = false,
    /** La vista está aislada: el interruptor ofrecerá volver a verlo todo. */
    val localView: Boolean = false,
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
 * Tanto en Object como en Edit se pintan como el mismo anillo radial
 * ([com.blendertablet.remote.ui.QuickMenu]); esta clase es la fuente única en
 * ambos casos.
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
                add(ActionId.RENAME)
                add(ActionId.HIDE_OBJECT)
                add(ActionId.VIEW_LOCAL)
                if (context.objectShadingAvailable) add(ActionId.SHADE_OBJECT)
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
                if (context.hasSelection) {
                    add(ActionId.HIDE_OBJECT)
                    add(ActionId.VIEW_LOCAL)
                }
            }
        }
        // Borrar solo si hay algo que borrar, y siempre el último: es el destructivo.
        if (context.objectSelected || (!context.hit && context.hasSelection)) add(ActionId.DELETE)
    }

    private fun editActions(context: TouchContext): List<ActionId> = buildList {
        // Caja y Círculo arman el arrastre por forma: selección pura, va primero.
        // Con selección, Borrar sustituye a Seleccionar todo: así el destructivo
        // contextual cabe también en Aristas sin superar el tope de ocho sectores.
        add(ActionId.TOOL_BOX)
        add(ActionId.TOOL_CIRCLE)
        if (!context.hasSelection) add(ActionId.SELECT_ALL)

        // En caras el último toque conserva también la dirección topológica de la
        // arista más próxima, igual que Alt+click en Blender.
        if (context.selectionMode in setOf(SelectionMode.EDGE, SelectionMode.FACE) && context.hasSelection) {
            add(ActionId.SELECT_LOOP)
            add(ActionId.SELECT_RING)
        }
        // Enlazado (la `L`) siembra con lo seleccionado: sin semilla no hay isla.
        if (context.hasSelection) {
            add(ActionId.SELECT_LINKED)
            add(ActionId.HIDE_GEOMETRY)
        }
        // "Mostrar oculto" salió del anillo: es raro comparado con lo demás y no
        // cabía junto a Enlazado en Aristas, donde el tope de ocho ya iba lleno.
        // Sigue a un toque, dentro de "Tools de malla".

        // El sector destructivo abre dos intenciones distintas: Borrar y Disolver.
        // No se gastan dos sectores ni se confunde disolver con ONLY_FACES.
        if (context.hasSelection) add(ActionId.DELETE)

        // Separar/Split/Normales/Bevel/Subdivide/Bridge y demás viven en el catálogo
        // de vértice/arista/cara, detrás de un único sector. Borrar se mantiene fuera
        // porque es frecuente y depende directamente del submodo activo.
        add(ActionId.EDIT_MESH_TOOLS)
    }
}
