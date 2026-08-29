package com.blendertablet.remote

import com.blendertablet.remote.model.BlenderMode
import com.blendertablet.remote.network.duplicateCommand
import com.blendertablet.remote.network.duplicateNotice
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class DuplicateRoutingTest {
    @Test fun `duplicar usa objetos en Object y seleccion de malla en Edit`() {
        assertEquals("object.duplicate", duplicateCommand(BlenderMode.OBJECT))
        assertEquals("mesh.duplicate", duplicateCommand(BlenderMode.EDIT))
    }

    private fun meshResult(verts: Int, edges: Int, faces: Int) = org.json.JSONObject(
        """{"object":"Cube","duplicated":{"verts":$verts,"edges":$edges,"faces":$faces}}"""
    )

    @Test fun `el aviso nombra la unidad del submodo, no la topologia completa`() {
        // Duplicar una cara arrastra sus 4 aristas y 4 vértices: el usuario duplicó
        // una cara, y eso es lo que tiene que leer.
        assertEquals("1 cara duplicada", duplicateNotice("mesh.duplicate", meshResult(4, 4, 1)))
        assertEquals("1 arista duplicada", duplicateNotice("mesh.duplicate", meshResult(2, 1, 0)))
        assertEquals("1 vértice duplicado", duplicateNotice("mesh.duplicate", meshResult(1, 0, 0)))
    }

    @Test fun `el aviso pluraliza`() {
        assertEquals("3 caras duplicadas", duplicateNotice("mesh.duplicate", meshResult(8, 10, 3)))
        assertEquals("2 aristas duplicadas", duplicateNotice("mesh.duplicate", meshResult(4, 2, 0)))
        assertEquals("5 vértices duplicados", duplicateNotice("mesh.duplicate", meshResult(5, 0, 0)))
    }

    @Test fun `en Object cuenta los objetos creados`() {
        assertEquals("1 objeto duplicado", duplicateNotice(
            "object.duplicate", org.json.JSONObject("""{"created":["Cube.001"]}""")))
        assertEquals("2 objetos duplicados", duplicateNotice(
            "object.duplicate", org.json.JSONObject("""{"created":["Cube.001","Cube.002"]}""")))
    }

    @Test fun `sin duplicado no hay aviso`() {
        assertNull(duplicateNotice("mesh.duplicate", meshResult(0, 0, 0)))
        assertNull(duplicateNotice("object.duplicate", org.json.JSONObject("""{"created":[]}""")))
        assertNull(duplicateNotice("mesh.duplicate", null))
        // Cualquier otro comando pasa por el mismo punto del dispatcher.
        assertNull(duplicateNotice("mesh.delete", org.json.JSONObject("""{"deleted":"FACES"}""")))
    }
}
