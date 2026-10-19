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

    @Test fun loopPositionAcceptsExactUnitsAndExpressionsFromItsCentre() {
        assertEquals(.25,parseLoopPosition("25%",0.0,.02)!!,1e-9)
        assertEquals(.25,parseLoopPosition("5mm",0.0,.02)!!,1e-9)
        assertEquals(.5,parseLoopPosition("(2+3)*2mm",0.0,.02)!!,1e-9)
        assertEquals(.30,parseLoopPosition("+1mm",.25,.02)!!,1e-9)
        assertEquals(-.5,parseLoopPosition("-1cm",0.0,.02)!!,1e-9)
        assertNull(parseLoopPosition("",0.0,.02));assertNull(parseLoopPosition("5mm",0.0,0.0))
        val simple=toolTrayContents(ToolSession(tool=EditTool.LOOP_CUT))
        assertFalse("falloff" in simple.advanced);assertFalse("flip" in simple.advanced)
        val curved=toolTrayContents(ToolSession(tool=EditTool.LOOP_CUT,parameters=mapOf("smoothness" to .5,"even" to true)))
        assertTrue("falloff" in curved.advanced);assertTrue("flip" in curved.advanced)
    }

    @Test fun bevelShowsOnlyWidthAndSegmentsAndHidesIneffectiveProfile() {
        val one=toolTrayContents(ToolSession(tool=EditTool.BEVEL,parameters=mapOf("segments" to 1)))
        assertEquals(listOf("offset","segments","more"),one.visible)
        assertFalse("profile" in one.advanced)
        val many=toolTrayContents(ToolSession(tool=EditTool.BEVEL,parameters=mapOf("segments" to 3)),SelectionMode.VERTEX)
        assertTrue("profile" in many.advanced);assertFalse("miter_outer" in many.advanced)
        assertTrue("miter_outer" in toolTrayContents(ToolSession(tool=EditTool.BEVEL),SelectionMode.FACE).advanced)
    }

    @Test fun extrudeKeepsOnlyDistanceAndAxisAndParsesTypedUnitsAtAnySceneScale() {
        val free=toolTrayContents(ToolSession(tool=EditTool.EXTRUDE))
        assertEquals(listOf("offset","constraint","more"),free.visible)
        assertFalse("orientation" in free.advanced)
        assertTrue("orientation" in toolTrayContents(ToolSession(tool=EditTool.EXTRUDE,parameters=mapOf("constraint" to "X"))).advanced)
        assertFalse("constraint" in toolTrayContents(ToolSession(tool=EditTool.EXTRUDE,parameters=mapOf("variant" to "INDIVIDUAL"))).visible)
        assertEquals(5.0,parseToolValue("5mm",10.0,TransformMode.MOVE,LengthUnit.CENTIMETERS,.001)!!,1e-9)
        assertEquals(11.0,parseToolValue("+1mm",10.0,TransformMode.MOVE,LengthUnit.CENTIMETERS,.001)!!,1e-9)
        assertEquals(20.0,parseToolValue("2",10.0,TransformMode.MOVE,LengthUnit.CENTIMETERS,.001)!!,1e-9)
        assertEquals(.25,parseToolValue("25%",.5,TransformMode.SCALE,null,1.0)!!,1e-9)
        assertNull(parseToolValue("",10.0,TransformMode.MOVE,LengthUnit.CENTIMETERS,.001))
    }

    @Test fun insetBridgeAndSubdivideKeepOnlyEffectiveParametersInTheirMainRow() {
        assertEquals(listOf("thickness","more"),toolTrayContents(ToolSession(tool=EditTool.INSET)).visible)
        val joined=toolTrayContents(ToolSession(tool=EditTool.BRIDGE_EDGE_LOOPS))
        assertEquals(listOf("twist_offset","more"),joined.visible)
        assertFalse("merge_factor" in joined.advanced)
        val merged=toolTrayContents(ToolSession(tool=EditTool.BRIDGE_EDGE_LOOPS,parameters=mapOf("merge" to true)))
        assertEquals(listOf("merge_factor","more"),merged.visible)
        assertTrue("twist_offset" in merged.advanced)
        assertEquals(listOf("cuts","more"),toolTrayContents(ToolSession(tool=EditTool.SUBDIVIDE)).visible)
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
