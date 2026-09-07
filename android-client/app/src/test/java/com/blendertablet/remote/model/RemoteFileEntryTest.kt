package com.blendertablet.remote.model

import org.junit.Assert.*
import org.junit.Test

class RemoteFileEntryTest {
    @Test fun directoryAliasesHaveDifferentStableRowsEvenWithOneCanonicalTarget() {
        val entries = listOf("lib", "lib64", "usr-lib").map {
            RemoteFileEntry(it, "/usr/lib", RemoteFileType.DIRECTORY)
        }
        assertEquals(entries.size, entries.map { it.rowKey }.toSet().size)
        assertEquals(entries.first().rowKey, entries.reversed().last().rowKey)
    }
    @Test fun opaquePathsAndNamesCannotCollideAtTheirBoundary() {
        val first = RemoteFileEntry("a", "bc", RemoteFileType.DIRECTORY)
        val second = RemoteFileEntry("ab", "c", RemoteFileType.DIRECTORY)
        assertNotEquals(first.rowKey, second.rowKey)
    }
}
