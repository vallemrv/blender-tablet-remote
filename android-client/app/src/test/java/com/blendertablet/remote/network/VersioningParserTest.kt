package com.blendertablet.remote.network

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class VersioningParserTest {
    @Test fun tokenIsNotPartOfTabletStateAndHistoryIsStructured() {
        val value = VersioningParser.state(JSONObject("""{"available":true,"ready":true,"busy":false,"branch":"main",
            "account":{"server":"https://git.example","username":"valle","has_token":true,"token":"never-display"},
            "commits":[{"id":"abc","date":"2026-10-18","message":"Versión con comillas \\\" y símbolos","author":"Valle"}]}"""))
        assertTrue(value.ready);assertTrue(value.account.hasToken)
        assertEquals("valle", value.account.username);assertEquals("abc", value.commits.single().id)
        assertFalse(value.toString().contains("never-display"))
        assertNull(value.error)
    }
    @Test fun historyCanShowOneIdeaWhileAnotherRemainsActive() {
        val state = VersioningParser.state(JSONObject("""{"available":true,"ready":true,
            "branch":"ideas/prueba","head":"new","history_branch":"main","primary_branch":"main",
            "branches":[{"name":"main","tip":"original","label":"Principal","active":false},
                        {"name":"ideas/prueba","tip":"new","label":"prueba","active":true,"base":"shared"}],
            "commits":[{"id":"original","date":"2026-10-18","message":"Paso original","author":"Valle","parents":["shared"]}]}"""))
        assertEquals("ideas/prueba",state.branch);assertEquals("main",state.historyBranch)
        assertEquals("new",state.head);assertEquals("shared",state.branches.last().base)
        assertTrue(state.branches.last().active);assertFalse(state.branches.first().active)
        assertEquals(listOf("shared"),state.commits.single().parents)
    }
    @Test fun disconnectedAndEmptyStatesHaveSafeDefaults() {
        val state = VersioningParser.state(JSONObject("{}"))
        assertFalse(state.busy);assertFalse(state.ready);assertFalse(state.lfsAvailable)
        assertTrue(state.commits.isEmpty());assertFalse(state.account.hasToken)
        assertFalse(StateParser.features(JSONObject("{}" )).versioning)
        assertTrue(StateParser.features(JSONObject("""{"features":{"versioning":{"version":1}}}""")).versioning)
    }
}
