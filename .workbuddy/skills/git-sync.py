#!/usr/bin/env python3
"""
足球技能 Git 同步工具（API 版）
用法：
  python3 git-sync.py push   # 推送本地更改到 GitHub
  python3 git-sync.py pull    # 拉取 GitHub 最新到本地
  python3 git-sync.py status  # 比较本地和远程差异

原理：通过 GitHub REST API 操作，绕过被墙的 github.com:443
"""
import os
import sys
import json
import base64
import urllib.request
import urllib.error
import shutil
from datetime import datetime

def _load_token():
    """从环境变量或本地文件读取 token，绝不硬编码。"""
    tok = os.environ.get("GITHUB_TOKEN", "")
    if tok:
        return tok
    cand = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "..", "..", "..", "data-pipeline", ".git_token")
    try:
        with open(cand) as f:
            return f.read().strip()
    except Exception:
        return ""

TOKEN = _load_token()
GITHUB_USER = "1442334458-eng"
API_BASE = "https://api.github.com"

# 技能文件夹映射：(本地目录, GitHub 仓库名)
REPOS = [
    ("football-betting-analysis", "football-betting-analysis"),
    ("football-match-analysis__skillhub", "football-match-analysis"),
    ("football-pipeline-v8", "football-pipeline-v8"),
]

EXCLUDE_PATTERNS = ["~syncthing~", ".sync-conflict-", ".sync-conflict", ".env", ".env.local"]
EXCLUDE_DIRS = {".git", "__pycache__", ".pytest_cache", "cache", "logs", ".stfolder", ".stversions"}

# 额外同步任务：将独立技能文件/外部文件映射到已有仓库
# local_path 可以是相对路径（相对于 skills_dir）或绝对路径
EXTRA_SYNC = [
    {"repo_name": "football-betting-analysis", "repo_path": "football-sync/SKILL.md", "local_path": "football-sync/SKILL.md"},
    {"repo_name": "football-betting-analysis", "repo_path": "球队画像档案库_v2.0.md", "local_path": "D:/1/Claw/球队画像档案库_v2.0.md"},
    {"repo_name": "football-betting-analysis", "repo_path": "git-sync.py", "local_path": "git-sync.py"},
    # jc-mcp MCP 配置同步（两台电脑必须一致）
    {"repo_name": "football-betting-analysis", "repo_path": ".mcp.json", "local_path": "C:/Users/xieyu/.workbuddy/.mcp.json"},
]


def should_exclude(filename):
    return any(p in filename for p in EXCLUDE_PATTERNS)


def api_request(method, path, data=None, raw=False):
    url = f"{API_BASE}{path}"
    headers = {
        "Authorization": f"token {TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json",
    }
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            if raw:
                return resp.read()
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        print(f"  API Error {e.code}: {error_body[:300]}")
        raise
    except urllib.error.URLError as e:
        print(f"  Network Error: {e}")
        raise


def collect_local_files(skill_dir):
    """Walk local directory and collect all files."""
    files = []
    for root, dirs, files_list in os.walk(skill_dir):
        # Skip excluded dirs
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for f in files_list:
            if should_exclude(f):
                continue
            full_path = os.path.join(root, f)
            rel_path = os.path.relpath(full_path, skill_dir).replace("\\", "/")
            files.append((rel_path, full_path))
    return sorted(files, key=lambda x: x[0])


def get_remote_tree(owner, repo, branch="main"):
    """Get all files from remote repo recursively."""
    try:
        result = api_request("GET", f"/repos/{owner}/{repo}/git/trees/{branch}?recursive=1")
        return result
    except Exception as e:
        print(f"  无法获取远程文件树: {e}")
        return None


def read_file_content(full_path):
    """Read file, return (content, encoding)."""
    with open(full_path, "rb") as f:
        raw = f.read()
    try:
        return raw.decode("utf-8"), "utf-8", len(raw)
    except UnicodeDecodeError:
        return base64.b64encode(raw).decode("ascii"), "base64", len(raw)


def write_file_content(full_path, content, encoding):
    """Write file with given content and encoding."""
    os.makedirs(os.path.dirname(full_path), exist_ok=True) if os.path.dirname(full_path) != skill_dir_base else None
    if encoding == "base64":
        raw = base64.b64decode(content)
    else:
        raw = content.encode("utf-8")
    with open(full_path, "wb") as f:
        f.write(raw)


def do_push(owner, repo, skill_dir):
    """Push local files to GitHub via API."""
    print(f"\n--- Push {repo} ---")
    local_files = collect_local_files(skill_dir)
    print(f"  本地文件: {len(local_files)} 个")

    # Create blobs
    tree_items = []
    for rel_path, full_path in local_files:
        content, encoding, size = read_file_content(full_path)
        tag = "[bin]" if encoding == "base64" else "[txt]"
        print(f"  {tag} {rel_path} ({size} bytes)")
        blob_data = {"content": content, "encoding": encoding}
        blob = api_request("POST", f"/repos/{owner}/{repo}/git/blobs", blob_data)
        tree_items.append({"path": rel_path, "mode": "100644", "type": "blob", "sha": blob["sha"]})

    # Create tree
    tree_result = api_request("POST", f"/repos/{owner}/{repo}/git/trees", {"tree": tree_items})
    print(f"  Tree: {tree_result['sha'][:12]}")

    # Get parent commit
    parent_sha = None
    try:
        refs = api_request("GET", f"/repos/{owner}/{repo}/git/refs/heads/main")
        parent_sha = refs["object"]["sha"]
        print(f"  Parent: {parent_sha[:12]}")
    except Exception:
        print("  无父提交（首次提交）")

    # Create commit
    commit_data = {"message": f"更新 {datetime.now().strftime('%Y-%m-%d %H:%M')}", "tree": tree_result["sha"]}
    if parent_sha:
        commit_data["parents"] = [parent_sha]
    commit_result = api_request("POST", f"/repos/{owner}/{repo}/git/commits", commit_data)
    print(f"  Commit: {commit_result['sha'][:12]}")

    # Update ref
    try:
        api_request("PATCH", f"/repos/{owner}/{repo}/git/refs/heads/main", {"sha": commit_result["sha"], "force": True})
    except Exception:
        api_request("POST", f"/repos/{owner}/{repo}/git/refs", {"sha": commit_result["sha"], "ref": "refs/heads/main"})

    print(f"  Push 完成!")


def do_pull(owner, repo, skill_dir):
    """Pull remote files to local via API."""
    print(f"\n--- Pull {repo} ---")
    tree = get_remote_tree(owner, repo, "main")
    if not tree:
        return

    remote_files = [t for t in tree.get("tree", []) if t["type"] == "blob"]
    print(f"  远程文件: {len(remote_files)} 个")

    for item in remote_files:
        path = item["path"]
        sha = item["sha"]
        # Get blob content
        blob = api_request("GET", f"/repos/{owner}/{repo}/git/blobs/{sha}")
        encoding = blob["encoding"]
        content = blob["content"]

        full_path = os.path.join(skill_dir, path.replace("/", os.sep))
        os.makedirs(os.path.dirname(full_path), exist_ok=True) if os.path.dirname(full_path) != skill_dir else None

        if encoding == "base64":
            raw = base64.b64decode(content)
        else:
            raw = content.encode("utf-8")

        with open(full_path, "wb") as f:
            f.write(raw)
        print(f"  [ok] {path} ({len(raw)} bytes)")

    print(f"  Pull 完成!")


def do_status(owner, repo, skill_dir):
    """Compare local and remote files."""
    print(f"\n--- Status {repo} ---")
    local_files = collect_local_files(skill_dir)
    local_set = {f[0] for f in local_files}

    tree = get_remote_tree(owner, repo, "main")
    if not tree:
        return
    remote_files = [t for t in tree.get("tree", []) if t["type"] == "blob"]
    remote_set = {t["path"] for t in remote_files}

    # Files only local
    local_only = local_set - remote_set
    # Files only remote
    remote_only = remote_set - local_set
    # Common files (would need to check content for actual diff)
    common = local_set & remote_set

    if local_only:
        print(f"  仅本地 ({len(local_only)}):")
        for f in sorted(local_only):
            print(f"    + {f}")
    if remote_only:
        print(f"  仅远程 ({len(remote_only)}):")
        for f in sorted(remote_only):
            print(f"    - {f}")
    if not local_only and not remote_only:
        print(f"  文件列表一致 ({len(common)} 个文件)")
        print(f"  注意：未比较文件内容，如有修改请 push")


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("push", "pull", "status"):
        print("用法: python3 git-sync.py [push|pull|status]")
        sys.exit(1)

    action = sys.argv[1]
    skills_dir = os.path.expanduser("~/.workbuddy/skills")

    print(f"{'='*60}")
    print(f"足球技能同步 — {action.upper()}")
    print(f"{'='*60}")

    for local_name, repo_name in REPOS:
        skill_dir = os.path.join(skills_dir, local_name)
        global skill_dir_base
        skill_dir_base = skill_dir
        if not os.path.isdir(skill_dir):
            print(f"\n跳过 {local_name}（目录不存在）")
            continue
        try:
            if action == "push":
                for extra in EXTRA_SYNC:
                    if extra["repo_name"] == repo_name:
                        local_path = extra["local_path"]
                        src = local_path if os.path.isabs(local_path) else os.path.join(skills_dir, local_path)
                        dst = os.path.join(skill_dir, extra["repo_path"])
                        if os.path.exists(src):
                            os.makedirs(os.path.dirname(dst), exist_ok=True)
                            shutil.copy2(src, dst)
                            print(f"  [sync] 已拷贝 {extra['local_path']} → {extra['repo_path']}")
                do_push(GITHUB_USER, repo_name, skill_dir)
            elif action == "pull":
                do_pull(GITHUB_USER, repo_name, skill_dir)
                for extra in EXTRA_SYNC:
                    if extra["repo_name"] == repo_name:
                        src = os.path.join(skill_dir, extra["repo_path"])
                        local_path = extra["local_path"]
                        dst = local_path if os.path.isabs(local_path) else os.path.join(skills_dir, local_path)
                        if os.path.exists(src):
                            os.makedirs(os.path.dirname(dst), exist_ok=True)
                            shutil.copy2(src, dst)
                            print(f"  [sync] 已还原 {extra['local_path']}")
            elif action == "status":
                do_status(GITHUB_USER, repo_name, skill_dir)
        except Exception as e:
            print(f"  操作失败: {e}")

    print(f"\n{'='*60}")
    if action == "push":
        print("⚠️  提醒：另一台电脑需要执行 pull 来获取本次更新！")
    elif action == "pull":
        # 写入 pull 时间戳，供时效检查使用
        timestamp_file = os.path.join(skills_dir, ".last_pull_time")
        with open(timestamp_file, "w") as f:
            f.write(datetime.now().isoformat())
    print("完成!")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
