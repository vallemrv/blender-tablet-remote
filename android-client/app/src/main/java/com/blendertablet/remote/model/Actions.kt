package com.blendertablet.remote.model

/**
 * Catálogo de acciones y su superficie propietaria.
 *
 * Invariante de la interfaz (§ "cero duplicidades"): cada acción existe en **una
 * sola superficie visible**. La excepción son los gestos, que pueden invocar una
 * acción que ya tenga un control visible porque no ocupan otro menú (p. ej. el doble
 * toque ejecuta "Encuadrar selección").
 *
 * Este catálogo es la única tabla `acción → superficie`, y no es decorativo: el menú
 * radial se construye con [RadialMenu.actionsFor], que devuelve [ActionId]s, y el test
 * comprueba que **todo lo que ese constructor puede emitir pertenece a RADIAL**. Así
 * el invariante se verifica contra el código que dibuja el menú, no contra una lista
 * escrita a mano en paralelo.
 */
enum class ActionSurface { TOP, TOP_DYNAMIC, TOP_TOOLS, TOP_MODE, RAIL, FOOTER, FOOTER_VIEWS, FOOTER_EDIT, RADIAL, MODIFIER_PANEL }

enum class ActionId {
    // Top: operaciones poco frecuentes o globales.
    FILE_NEW,
    FILE_OPEN,
    FILE_SAVE,
    FILE_SAVE_AS,
    CURSOR_SNAP,
    CONNECTION_SETTINGS,
    RECONNECT,
    DISCONNECT,

    // Barra de modo (junto al ojo): Object/Edit, fuera del rail.
    MODE_OBJECT,
    MODE_EDIT,

    // Rail: elegir la herramienta activa y el submodo de selección.
    TOOL_SELECT,
    TOOL_MOVE,
    TOOL_ROTATE,
    TOOL_SCALE,
    TOOL_EXTRUDE,
    TOOL_BEVEL,
    TOOL_INSET,
    TOOL_SUBDIVIDE,
    SEL_VERTEX,
    SEL_EDGE,
    SEL_FACE,
    UNDO,
    REDO,
    DUPLICATE,
    TOOL_LOOP_CUT,

    // Barra superior de tools: junto al ojo.
    VIEW_SHADING,

    // Footer: opciones de la herramienta activa.
    CONSTRAINT,
    ORIENTATION,
    SNAP_TYPE,
    SNAP_STEP,
    VALUE,
    VALUE_MODE,
    TRANSFORM_CONFIRM,
    TRANSFORM_CANCEL,

    // Footer de vistas: navegación rápida.
    VIEW_FRONT,
    VIEW_BACK,
    VIEW_LEFT,
    VIEW_RIGHT,
    VIEW_TOP,
    VIEW_BOTTOM,
    VIEW_PROJECTION,
    VIEW_FRAME_ALL,
    VIEW_LOCAL,
    SELECT_MORE,
    SELECT_LESS,

    // Página Edit del footer. No son entradas del menú contextual: el catálogo
    // remoto decide allí qué operaciones existen; estas fijan su única superficie.
    EDIT_MAKE_EDGE_FACE,
    EDIT_KNIFE,
    EDIT_SEPARATE,
    EDIT_SPLIT,
    EDIT_NORMALS,

    // Radial (pulsación larga): acciones contextuales frecuentes, no duplicadas.
    ADD_OBJECT,
    TOOL_BOX,
    TOOL_CIRCLE,
    SELECT_ALL,
    DESELECT_ALL,
    SELECT_INVERT,
    SELECT_UNDER,
    SELECT_ADD_UNDER,
    SELECT_LOOP,
    SELECT_RING,
    HIDE_OBJECT,
    HIDE_GEOMETRY,
    REVEAL_GEOMETRY,
    DUPLICATE_LINKED,
    RENAME,
    DELETE,
    DISSOLVE,
    APPLY_TRANSFORMS,
    SET_ORIGIN,
    SHOW_HIDDEN_OBJECT,
    SHOW_ALL_HIDDEN_OBJECTS,
    APPLY_LOCATION,
    APPLY_ROTATION,
    APPLY_SCALE,
    MODIFIER_ADD,
    MODIFIER_SET,
    MODIFIER_TOGGLE,
    MODIFIER_MOVE,
    MODIFIER_APPLY,
    MODIFIER_REMOVE,
}

/** Una fila del catálogo: acción, dónde vive y su etiqueta visible. */
data class ActionEntry(val id: ActionId, val surface: ActionSurface, val label: String)

object SurfaceCatalog {

    val entries: List<ActionEntry> = listOf(
        // Top
        ActionEntry(ActionId.FILE_NEW, ActionSurface.TOP, "Nuevo"),
        ActionEntry(ActionId.FILE_OPEN, ActionSurface.TOP, "Abrir"),
        ActionEntry(ActionId.FILE_SAVE, ActionSurface.TOP, "Guardar"),
        ActionEntry(ActionId.FILE_SAVE_AS, ActionSurface.TOP, "Guardar como"),
        ActionEntry(ActionId.CURSOR_SNAP, ActionSurface.TOP, "Cursor y selección"),
        ActionEntry(ActionId.CONNECTION_SETTINGS, ActionSurface.TOP, "Preferencias"),
        ActionEntry(ActionId.RECONNECT, ActionSurface.TOP, "Reconectar"),
        ActionEntry(ActionId.DISCONNECT, ActionSurface.TOP, "Desconectar"),

        // Rail
        ActionEntry(ActionId.TOOL_SELECT, ActionSurface.RAIL, "Seleccionar"),
        ActionEntry(ActionId.TOOL_MOVE, ActionSurface.RAIL, "Mover"),
        ActionEntry(ActionId.TOOL_ROTATE, ActionSurface.RAIL, "Rotar"),
        ActionEntry(ActionId.TOOL_SCALE, ActionSurface.RAIL, "Escalar"),
        ActionEntry(ActionId.TOOL_EXTRUDE, ActionSurface.RAIL, "Extruir"),
        ActionEntry(ActionId.TOOL_BEVEL, ActionSurface.RAIL, "Bisel"),
        ActionEntry(ActionId.TOOL_INSET, ActionSurface.RAIL, "Inset"),
        ActionEntry(ActionId.TOOL_SUBDIVIDE, ActionSurface.RAIL, "Subdividir"),
        ActionEntry(ActionId.DUPLICATE, ActionSurface.RAIL, "Duplicar"),
        ActionEntry(ActionId.TOOL_LOOP_CUT, ActionSurface.RAIL, "Loop Cut"),

        // Barra de modo: Object/Edit, junto al ojo. Salieron del rail para dejarlo
        // dedicado a herramientas.
        ActionEntry(ActionId.MODE_OBJECT, ActionSurface.TOP_MODE, "Object Mode"),
        ActionEntry(ActionId.MODE_EDIT, ActionSurface.TOP_MODE, "Edit Mode"),

        // Barra superior de tools: junto al ojo (wireframe, Ctrl/Alt, undo/redo) y,
        // en Edit Mode, el submodo de selección. B/C viven en el long-click (RADIAL).
        ActionEntry(ActionId.VIEW_SHADING, ActionSurface.TOP_TOOLS, "Wireframe"),
        ActionEntry(ActionId.UNDO, ActionSurface.TOP_TOOLS, "Deshacer"),
        ActionEntry(ActionId.REDO, ActionSurface.TOP_TOOLS, "Rehacer"),
        ActionEntry(ActionId.SEL_VERTEX, ActionSurface.TOP_TOOLS, "Vértice"),
        ActionEntry(ActionId.SEL_EDGE, ActionSurface.TOP_TOOLS, "Arista"),
        ActionEntry(ActionId.SEL_FACE, ActionSurface.TOP_TOOLS, "Cara"),

        // Footer de herramienta
        ActionEntry(ActionId.CONSTRAINT, ActionSurface.FOOTER, "Restricción"),
        ActionEntry(ActionId.ORIENTATION, ActionSurface.FOOTER, "Orientación"),
        ActionEntry(ActionId.SNAP_TYPE, ActionSurface.FOOTER, "Snap"),
        ActionEntry(ActionId.SNAP_STEP, ActionSurface.FOOTER, "Paso"),
        ActionEntry(ActionId.VALUE, ActionSurface.FOOTER, "Valor"),
        ActionEntry(ActionId.VALUE_MODE, ActionSurface.FOOTER, "Relativo/absoluto"),
        ActionEntry(ActionId.TRANSFORM_CONFIRM, ActionSurface.FOOTER, "Confirmar"),
        ActionEntry(ActionId.TRANSFORM_CANCEL, ActionSurface.FOOTER, "Descartar"),

        // Footer de vistas
        ActionEntry(ActionId.VIEW_FRONT, ActionSurface.FOOTER_VIEWS, "Front"),
        ActionEntry(ActionId.VIEW_BACK, ActionSurface.FOOTER_VIEWS, "Back"),
        ActionEntry(ActionId.VIEW_LEFT, ActionSurface.FOOTER_VIEWS, "Left"),
        ActionEntry(ActionId.VIEW_RIGHT, ActionSurface.FOOTER_VIEWS, "Right"),
        ActionEntry(ActionId.VIEW_TOP, ActionSurface.FOOTER_VIEWS, "Top"),
        ActionEntry(ActionId.VIEW_BOTTOM, ActionSurface.FOOTER_VIEWS, "Bottom"),
        ActionEntry(ActionId.VIEW_PROJECTION, ActionSurface.FOOTER_VIEWS, "Persp/Ortho"),
        ActionEntry(ActionId.VIEW_FRAME_ALL, ActionSurface.FOOTER_VIEWS, "Encuadrar todo"),
        ActionEntry(ActionId.VIEW_LOCAL, ActionSurface.FOOTER_VIEWS, "Aislar selección"),
        ActionEntry(ActionId.SELECT_MORE, ActionSurface.FOOTER_VIEWS, "Crecer selección"),
        ActionEntry(ActionId.SELECT_LESS, ActionSurface.FOOTER_VIEWS, "Decrecer selección"),

        ActionEntry(ActionId.EDIT_MAKE_EDGE_FACE, ActionSurface.FOOTER_EDIT, "Crear arista/cara"),
        ActionEntry(ActionId.EDIT_KNIFE, ActionSurface.FOOTER_EDIT, "Cuchillo"),
        ActionEntry(ActionId.EDIT_SEPARATE, ActionSurface.FOOTER_EDIT, "Separar a objeto"),
        ActionEntry(ActionId.EDIT_SPLIT, ActionSurface.FOOTER_EDIT, "Split"),
        ActionEntry(ActionId.EDIT_NORMALS, ActionSurface.FOOTER_EDIT, "Normales"),

        // Radial
        ActionEntry(ActionId.ADD_OBJECT, ActionSurface.RADIAL, "Agregar"),
        ActionEntry(ActionId.TOOL_BOX, ActionSurface.RADIAL, "Caja"),
        ActionEntry(ActionId.TOOL_CIRCLE, ActionSurface.RADIAL, "Círculo"),
        ActionEntry(ActionId.SELECT_ALL, ActionSurface.RADIAL, "Seleccionar todo"),
        ActionEntry(ActionId.DESELECT_ALL, ActionSurface.RADIAL, "Deseleccionar"),
        ActionEntry(ActionId.SELECT_INVERT, ActionSurface.RADIAL, "Invertir selección"),
        ActionEntry(ActionId.SELECT_UNDER, ActionSurface.RADIAL, "Seleccionar este"),
        ActionEntry(ActionId.SELECT_ADD_UNDER, ActionSurface.RADIAL, "Añadir a la selección"),
        ActionEntry(ActionId.SELECT_LOOP, ActionSurface.RADIAL, "Loop"),
        ActionEntry(ActionId.SELECT_RING, ActionSurface.RADIAL, "Ring"),
        ActionEntry(ActionId.HIDE_OBJECT, ActionSurface.RADIAL, "Ocultar objeto"),
        ActionEntry(ActionId.HIDE_GEOMETRY, ActionSurface.RADIAL, "Ocultar geometría"),
        ActionEntry(ActionId.REVEAL_GEOMETRY, ActionSurface.RADIAL, "Revelar geometría"),
        ActionEntry(ActionId.DUPLICATE_LINKED, ActionSurface.RADIAL, "Duplicar enlazado"),
        ActionEntry(ActionId.RENAME, ActionSurface.RADIAL, "Renombrar"),
        ActionEntry(ActionId.DELETE, ActionSurface.RADIAL, "Borrar"),
        ActionEntry(ActionId.DISSOLVE, ActionSurface.RADIAL, "Disolver"),
        ActionEntry(ActionId.APPLY_TRANSFORMS, ActionSurface.RADIAL, "Aplicar"),
        ActionEntry(ActionId.SET_ORIGIN, ActionSurface.RADIAL, "Establecer origen"),
        ActionEntry(ActionId.SHOW_HIDDEN_OBJECT, ActionSurface.TOP_DYNAMIC, "Mostrar objeto"),
        ActionEntry(ActionId.SHOW_ALL_HIDDEN_OBJECTS, ActionSurface.TOP_DYNAMIC, "Mostrar todos"),
        ActionEntry(ActionId.APPLY_LOCATION, ActionSurface.RADIAL, "Aplicar posición"),
        ActionEntry(ActionId.APPLY_ROTATION, ActionSurface.RADIAL, "Aplicar rotación"),
        ActionEntry(ActionId.APPLY_SCALE, ActionSurface.RADIAL, "Aplicar escala"),
        ActionEntry(ActionId.MODIFIER_ADD, ActionSurface.MODIFIER_PANEL, "Añadir modifier"),
        ActionEntry(ActionId.MODIFIER_SET, ActionSurface.MODIFIER_PANEL, "Editar modifier"),
        ActionEntry(ActionId.MODIFIER_TOGGLE, ActionSurface.MODIFIER_PANEL, "Visibilidad modifier"),
        ActionEntry(ActionId.MODIFIER_MOVE, ActionSurface.MODIFIER_PANEL, "Reordenar modifier"),
        ActionEntry(ActionId.MODIFIER_APPLY, ActionSurface.MODIFIER_PANEL, "Aplicar modifier"),
        ActionEntry(ActionId.MODIFIER_REMOVE, ActionSurface.MODIFIER_PANEL, "Eliminar modifier"),
    )

    /** Dónde vive una acción. Es la pregunta que hace el test de exclusividad. */
    fun surfaceOf(id: ActionId): ActionSurface = entries.first { it.id == id }.surface

    fun idsOf(surface: ActionSurface): List<ActionId> =
        entries.filter { it.surface == surface }.map { it.id }

    /** Acciones registradas en más de una superficie. Debería estar siempre vacío. */
    fun duplicates(): Map<ActionId, List<ActionSurface>> {
        val byId = entries.groupBy({ it.id }, { it.surface })
        return byId.filterValues { surfaces -> surfaces.distinct().size > 1 }
            .mapValues { (_, surfaces) -> surfaces.distinct() }
    }

    fun labelOf(id: ActionId): String = entries.first { it.id == id }.label
}
