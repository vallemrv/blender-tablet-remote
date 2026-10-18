package com.blendertablet.remote.model

data class SceneVersion(val id: String, val date: String, val message: String, val author: String, val parents: List<String> = emptyList())
data class VersionIdea(val name: String, val tip: String, val label: String, val active: Boolean = false, val base: String? = null)
data class GiteaAccount(val server: String = "", val username: String = "", val hasToken: Boolean = false,
    val authorName: String = "", val authorEmail: String = "", val allowHttp: Boolean = false)
data class VersioningState(
    val available: Boolean = false, val busy: Boolean = false, val ready: Boolean = false,
    val action: String = "", val source: String = "", val repoId: String? = null,
    val localPath: String = "", val branch: String = "", val remote: String = "",
    val lfsAvailable: Boolean = false, val sceneDirty: Boolean = false, val fileChanged: Boolean = false,
    val ahead: Int = 0, val behind: Int = 0,
    val message: String? = null, val error: String? = null,
    val account: GiteaAccount = GiteaAccount(), val commits: List<SceneVersion> = emptyList(),
    val head: String = "", val historyBranch: String = "", val primaryBranch: String = "",
    val branches: List<VersionIdea> = emptyList(),
)
