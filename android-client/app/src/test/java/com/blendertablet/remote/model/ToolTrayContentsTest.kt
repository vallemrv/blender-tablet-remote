package com.blendertablet.remote.model

import com.blendertablet.remote.data.reusableToolValues
import org.junit.Assert.*
import org.junit.Test

class ToolTrayContentsTest {
    @Test fun allRenderedInventoriesHaveAtMostFiveParameterGroupsAndNoDuplicates() {
        for (tool in EditTool.entries) for (mode in SelectionMode.entries) for (flag in listOf(false,true)) {
            val session = ToolSession(active=true, tool=tool, loopCount=if(flag) 3 else 1,
                parameters=mapOf("even" to flag,"smoothness" to if(flag) .5 else 0.0,"segments" to if(flag) 3 else 1,"merge" to flag,"constraint" to if(flag) "X" else "FREE"))
            val row=toolTrayContents(session,mode)
            assertTrue("$tool",row.visible.size <= 5)
            assertEquals(row.visible.size,row.visible.toSet().size)
            assertEquals("more",row.visible.last())
            assertTrue(row.visible.intersect(row.advanced.toSet()).isEmpty())
            assertFalse("snap" in row.visible)
        }
        val schema=ToolSession(controls=(1..20).map { EditCatalogParameter("p$it","p$it","float",primary=true) })
        assertEquals(4,toolTrayContents(schema).visible.size)
        assertEquals(17,toolTrayContents(schema).advanced.size)
    }

    @Test fun savedLengthsFollowPhysicalSizeAndNeverRestoreLoopLocationOrGeometryIds() {
        val stored=reusableToolValues(EditTool.BEVEL,mapOf("offset" to 5.0,"snap_step" to 1.0,"segments" to 3,"edge" to 55),.001,true)
        assertEquals(.005,stored["offset"])
        assertEquals(.005,reusableToolValues(EditTool.BEVEL,stored,1.0,false)["offset"])
        assertFalse("edge" in stored)
        val loop=reusableToolValues(EditTool.LOOP_CUT,mapOf("factor" to .5,"slide_distance" to .003,"cuts" to 3,"edge" to 44),1.0,true)
        assertEquals(mapOf("cuts" to 3),loop)
    }
}
