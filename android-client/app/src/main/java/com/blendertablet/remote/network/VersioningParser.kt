package com.blendertablet.remote.network

import com.blendertablet.remote.model.*
import org.json.JSONObject

internal object VersioningParser {
    fun state(j: JSONObject): VersioningState {
        val account = j.optJSONObject("account") ?: JSONObject()
        val commits = j.optJSONArray("commits")
        val branches = j.optJSONArray("branches")
        fun optional(key: String) = j.optString(key).takeIf { it.isNotBlank() && it != "null" }
        return VersioningState(available = j.optBoolean("available"), busy = j.optBoolean("busy"), ready = j.optBoolean("ready"),
            action = optional("action").orEmpty(), source = j.optString("source"), repoId = optional("repo_id"),
            localPath = j.optString("local_path"), branch = j.optString("branch"), remote = j.optString("remote"),
            lfsAvailable = j.optBoolean("lfs_available"), sceneDirty = j.optBoolean("scene_dirty"), fileChanged = j.optBoolean("file_changed"),
            ahead = j.optInt("ahead"), behind = j.optInt("behind"), message = optional("message"), error = optional("error"),
            account = GiteaAccount(account.optString("server"), account.optString("username"), account.optBoolean("has_token"),
                account.optString("author_name"), account.optString("author_email"), account.optBoolean("allow_http")),
            commits = (0 until (commits?.length() ?: 0)).map { index -> commits!!.getJSONObject(index).let {
                val parents = it.optJSONArray("parents")
                SceneVersion(it.getString("id"), it.optString("date"), it.optString("message"), it.optString("author"),
                    (0 until (parents?.length() ?: 0)).map { index -> parents!!.getString(index) })
            } }, head = j.optString("head"), historyBranch = j.optString("history_branch"), primaryBranch = j.optString("primary_branch"),
            branches = (0 until (branches?.length() ?: 0)).map { index -> branches!!.getJSONObject(index).let {
                VersionIdea(it.getString("name"), it.getString("tip"), it.optString("label", it.getString("name")),
                    it.optBoolean("active"), it.optString("base").takeIf { value -> value.isNotBlank() && value != "null" })
            } })
    }
}
