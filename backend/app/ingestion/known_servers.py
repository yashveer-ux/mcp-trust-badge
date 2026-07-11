"""Manifests for well-known real MCP servers whose tool lists are stable and
public (the official reference servers + GitHub). Used to seed the marketplace
with real, recognizable servers. Tool lists reflect documented capabilities.
"""
from __future__ import annotations

from app.core.manifest_schema import Tool, ToolManifest


def _t(name, desc, **schema):
    return Tool(name=name, description=desc, input_schema=schema)


KNOWN_SERVERS = [
    # modelcontextprotocol/servers — Filesystem
    ToolManifest(server_name="filesystem (modelcontextprotocol)", transport="stdio", tools=[
        _t("read_file", "read the contents of a file at a path", path="string"),
        _t("read_multiple_files", "read several files by path", paths="string[]"),
        _t("write_file", "create or overwrite a file at a path", path="string", content="string"),
        _t("edit_file", "make line edits to a text file at a path", path="string"),
        _t("create_directory", "create a directory at a path", path="string"),
        _t("list_directory", "list a directory at a path", path="string"),
        _t("directory_tree", "recursive tree of a directory path", path="string"),
        _t("move_file", "move or rename within allowed directories", source="string", destination="string"),
        _t("search_files", "search files under a directory path", path="string"),
        _t("get_file_info", "metadata for a file or directory path", path="string"),
    ]),

    # modelcontextprotocol/servers — Git
    ToolManifest(server_name="git (modelcontextprotocol)", transport="stdio", tools=[
        _t("git_status", "show working tree status of a repo path", repo_path="string"),
        _t("git_diff", "show diff for a repo path", repo_path="string"),
        _t("git_commit", "commit staged changes in a repo path", repo_path="string", message="string"),
        _t("git_add", "stage files in a repo path", repo_path="string"),
        _t("git_reset", "unstage changes in a repo path", repo_path="string"),
        _t("git_log", "show commit log for a repo path", repo_path="string"),
        _t("git_create_branch", "create a branch in a repo path", repo_path="string"),
        _t("git_checkout", "switch branches in a repo path", repo_path="string"),
    ]),

    # modelcontextprotocol/servers — Fetch
    ToolManifest(server_name="fetch (modelcontextprotocol)", transport="stdio", tools=[
        _t("fetch", "fetch a URL and return its contents as markdown", url="string", max_length="number"),
    ]),

    # modelcontextprotocol/servers — Memory (knowledge graph)
    ToolManifest(server_name="memory (modelcontextprotocol)", transport="stdio", tools=[
        _t("create_entities", "add entities to the knowledge graph"),
        _t("create_relations", "add relations between entities"),
        _t("add_observations", "attach observations to entities"),
        _t("delete_entities", "remove entities from the graph"),
        _t("read_graph", "read the whole knowledge graph"),
        _t("search_nodes", "search nodes in the graph", query="string"),
    ]),

    # modelcontextprotocol/servers — Time
    ToolManifest(server_name="time (modelcontextprotocol)", transport="stdio", tools=[
        _t("get_current_time", "get the current time in a timezone", timezone="string"),
        _t("convert_time", "convert a time between timezones"),
    ]),

    # modelcontextprotocol/servers — Sequential Thinking
    ToolManifest(server_name="sequential-thinking (modelcontextprotocol)", transport="stdio", tools=[
        _t("sequentialthinking", "record a step of structured reasoning", thought="string"),
    ]),

    # modelcontextprotocol/servers — Everything (test/reference server)
    ToolManifest(server_name="everything (modelcontextprotocol)", transport="stdio", tools=[
        _t("echo", "echo the input text", message="string"),
        _t("add", "add two numbers", a="number", b="number"),
        _t("printEnv", "print all environment variables"),
        _t("longRunningOperation", "demo a long operation"),
        _t("sampleLLM", "demo an LLM sampling request"),
    ]),

    # github/github-mcp-server
    ToolManifest(server_name="github (github/github-mcp-server)", transport="streamable-http", tools=[
        _t("get_file_contents", "read a file from a repo at a path", owner="string", repo="string", path="string"),
        _t("create_or_update_file", "write a file to a repo at a path", owner="string", repo="string", path="string", content="string"),
        _t("push_files", "push multiple files to a repo branch"),
        _t("create_issue", "open an issue in a repo", owner="string", repo="string", title="string"),
        _t("create_pull_request", "open a pull request in a repo"),
        _t("search_repositories", "search repositories", query="string"),
        _t("list_commits", "list commits on a branch"),
        _t("create_branch", "create a branch in a repo"),
    ]),
]
