#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通过 GitHub REST API 将本地项目推送到 GitHub（绕过 git 协议端口封锁）。

适用场景：沙箱环境 github.com:443 的 Git 协议端口被封，无法 git push。
改走 GitHub Git Data / Contents / Releases REST API 完成等效推送。

用法：
  python push_repo.py --repo <仓库名> [--path <目录>] [--private]
                      [--release v1.0.0] [--asset <附件路径>] ...
                      [--release-body-file <md文件>]
                      [--description "..."] [--topics a,b,c]
                      [--message <提交说明>] [--branch main]
                      [--allow-binary] [--no-verify]

设计原则：默认安全。
  - 只推送到「用户自己的仓库」，不做任何删除他人内容的操作。
  - 命中疑似密钥文件（.env / token / password / id_rsa / .pem / .workbuddy 等）
    一律中止，不可放行。
  - 命中二进制（.exe / .zip / .msi / .dll 等）默认中止，确需提交请显式加
    --allow-binary（建议改走 Release 附件分发，保持仓库轻量）。
"""
import argparse
import base64
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.github.com"
UPLOAD = "https://uploads.github.com"

# 命中即中止、不可放行（疑似密钥/私密数据）
HARD_RISK_KEYS = (".env", "secret", "password", "credential", "id_rsa",
                  ".pem", ".key", ".workbuddy", ".git-credentials")
# 命中需显式 --allow-binary 放行（二进制大文件）
SOFT_RISK_EXTS = (".exe", ".zip", ".7z", ".rar", ".msi", ".dll", ".so",
                  ".dylib", ".iso", ".bin", ".pfx", ".p12")


def get_token():
    """从 Windows 凭据管理器读取 GitHub token，不落盘。

    ⚠️ 必须在 -c 里先用空值 `credential.helper=` 重置 helper 列表，再指定目标 helper。

    原因：git 的 `credential.helper` 是**多值**配置，PortableGit 的 system 级
    (`etc/gitconfig`) 默认写了一条 `credential.helper = helper-selector`；
    它与用户级 `~/.gitconfig` 里的 helper 叠加后，列表里就有两个 helper，
    而 `helper-selector` 会弹出「Select a credential helper」图形窗口等人工点击
    —— 在无人值守环境会一直卡到超时（这正是"凭据读取偶发超时"的真因，
    不是网络慢）。

    注意 `-c credential.helper=X` 只是**追加**到列表末尾、不清空原有项，
    所以必须两个 `-c` 配合（先空值清空、再指定）才能把列表收敛成一个。

    若本机残留了 `credential.helperselector.selected` 且其值与真实 helper 名不匹配，
    selector 会每次重新弹窗 —— 需要在用户级 ~/.gitconfig 里做一次性清理
    （把 helper 列表用空值重置后只留一个），详见 references/notes.md 第二节。
    """
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    for helper in ("wincred", "manager", "manager-core"):
        args = ["git",
                "-c", "credential.helper=",          # 先清空，摘掉 system 的 helper-selector
                "-c", f"credential.helper={helper}",
                "credential", "fill"]
        try:
            p = subprocess.run(args,
                               input="protocol=https\nhost=github.com\n\n",
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=30, env=env)
        except Exception:
            continue
        for line in p.stdout.splitlines():
            if line.startswith("password="):
                return line[len("password="):].strip()

    # 兜底：完全不指定 helper，交给本机配置（前提是配置里只剩一个 helper，不会弹窗）
    try:
        p = subprocess.run(["git", "credential", "fill"],
                           input="protocol=https\nhost=github.com\n\n",
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=30, env=env)
    except Exception:
        return None
    for line in p.stdout.splitlines():
        if line.startswith("password="):
            return line[len("password="):].strip()
    return None


def api(method, path, token, data=None, base=API):
    url = (base + path) if path.startswith("/") else path
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "github-push-release",
    }
    body = None
    if data is not None:
        if isinstance(data, (dict, list)):
            body = json.dumps(data).encode("utf-8")
            headers["Content-Type"] = "application/json"
        else:  # 原始字节（附件上传）
            body = data
            headers["Content-Type"] = "application/octet-stream"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            code = r.getcode()
            raw = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        code = e.code
        raw = e.read().decode("utf-8", "replace")
    except Exception as e:  # 网络层错误
        return getattr(e, "code", 0), {"_error": str(e)}
    try:
        resp = json.loads(raw) if raw else {}
    except Exception:
        resp = {"_raw": raw}
    return code, resp


def tracked_files(repo_dir):
    """git add -A 后列出被跟踪文件（自动尊重 .gitignore）。

    关键：必须关闭 core.quotepath，否则 git 会把中文路径转义成
    \\344\\275\\277 这种八进制形式，导致 os.path.isfile 判定失败、
    文件被静默跳过。用 -z 以 NUL 分隔，彻底避免路径含空格/引号/
    换行带来的解析歧义。
    """
    subprocess.run(["git", "add", "-A"], cwd=repo_dir, capture_output=True)
    out = subprocess.run(["git", "-c", "core.quotepath=false", "ls-files", "-z"],
                         cwd=repo_dir, capture_output=True)
    return [b.decode("utf-8") for b in out.stdout.split(b"\0") if b.strip()]


def check_risky(files, allow_binary):
    """安全闸门：返回 (致命列表, 需放行列表)。"""
    hard, soft = [], []
    for f in files:
        low = f.lower()
        if any(k in low for k in HARD_RISK_KEYS):
            hard.append(f)
        elif low.endswith(SOFT_RISK_EXTS):
            soft.append(f)
    return hard, ([] if allow_binary else soft)


def verify(owner, repo, branch, repo_dir, token):
    """推送后核验：比对本地 git blob sha 与远程 tree 的 blob sha。

    注意：若本地文件是 CRLF 而 .gitattributes 声明 `* text=auto eol=lf`，
    本地 git 存的 blob 是 LF 版、而脚本按磁盘原始字节上传，两者 sha 会不同。
    统一磁盘换行符为 LF 即可让三方（磁盘 / 远程 / 本地 git）完全一致。
    """
    out = subprocess.run(["git", "ls-files", "-s", "-z"], cwd=repo_dir,
                         capture_output=True).stdout.split(b"\0")
    local = {}
    for line in out:
        if not line.strip():
            continue
        meta, path = line.split(b"\t", 1)
        _mode, sha, _stage = meta.split()  # 顺序是 mode sha stage
        local[path.decode("utf-8")] = sha.decode()

    code, d = api("GET",
                  f"/repos/{owner}/{repo}/git/trees/{branch}?recursive=1", token)
    if code != 200:
        print(f"[WARN] 远程文件树核验失败 code={code}")
        return
    remote = {n["path"]: n["sha"] for n in d.get("tree", []) if n["type"] == "blob"}

    only_local = sorted(set(local) - set(remote))
    only_remote = sorted(set(remote) - set(local))
    same = [f for f in local if f in remote and local[f] == remote[f]]
    diff = [f for f in local if f in remote and local[f] != remote[f]]

    print("=" * 56)
    print(f"[核验] 本地 {len(local)} 个文件 / 远程 {len(remote)} 个文件")
    print(f"[核验] 逐字节哈希一致: {len(same)} / {len(local)}")
    if only_local:
        print("[核验] 仅本地有（未推送成功）:")
        for f in only_local:
            print("   -", f)
    if only_remote:
        print("[核验] 仅远程有:")
        for f in only_remote:
            print("   -", f)
    if diff:
        print("[核验] 哈希不同（多为 CRLF/LF 换行符差异）:")
        for f in diff:
            print(f"   - {f}  本地={local[f][:8]} 远程={remote[f][:8]}")
    if not (only_local or only_remote or diff):
        print("[核验] 本地与远程逐字节完全一致 ✓")
    print("=" * 56)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--path", default=os.getcwd())
    ap.add_argument("--private", action="store_true")
    ap.add_argument("--release", default=None, help="版本标签 e.g. v1.0.0")
    ap.add_argument("--asset", action="append", default=[],
                    help="Release 附件路径，可重复传入多个")
    ap.add_argument("--release-body", default=None, help="Release 说明正文")
    ap.add_argument("--release-body-file", default=None,
                    help="从 UTF-8 文件读取 Release 说明（避免长中文 argv 转义）")
    ap.add_argument("--description", default=None, help="仓库描述")
    ap.add_argument("--topics", default=None, help="仓库 topics，逗号分隔")
    ap.add_argument("--message", default="Update via github-push-release")
    ap.add_argument("--branch", default="main")
    ap.add_argument("--allow-binary", action="store_true",
                    help="允许提交 .exe/.zip 等二进制（默认中止）")
    ap.add_argument("--no-verify", action="store_true", help="跳过推送后一致性核验")
    args = ap.parse_args()

    token = get_token()
    if not token:
        print("[ERR] 未在本机凭据管理器找到 GitHub token（wincred）。", file=sys.stderr)
        sys.exit(2)
    print("[ok] 已读取 GitHub token（未落盘）")

    code, me = api("GET", "/user", token)
    if code != 200:
        print("[ERR] 获取用户信息失败:", code, me)
        sys.exit(3)
    owner = me["login"]
    print(f"[ok] 登录账号: {owner}")

    repo_dir = os.path.abspath(args.path)

    if not os.path.isdir(os.path.join(repo_dir, ".git")):
        subprocess.run(["git", "init", "-b", args.branch], cwd=repo_dir,
                       capture_output=True)
        print("[ok] 已 git init")

    code, _ = api("GET", f"/repos/{owner}/{args.repo}", token)
    if code == 404:
        payload = {"name": args.repo, "private": args.private,
                   "auto_init": False}
        if args.description:
            payload["description"] = args.description
        else:
            payload["description"] = "Pushed via github-push-release"
        code, resp = api("POST", "/user/repos", token, payload)
        if code not in (200, 201):
            print("[ERR] 创建仓库失败:", code, resp)
            sys.exit(4)
        print(f"[ok] 已创建仓库 {owner}/{args.repo}")
    elif code == 200:
        print(f"[ok] 仓库已存在 {owner}/{args.repo}")
    else:
        print("[ERR] 检查仓库失败:", code)
        sys.exit(4)

    # 仓库元信息：描述 + topics
    if args.description:
        code, _r = api("PATCH", f"/repos/{owner}/{args.repo}", token,
                       {"description": args.description})
        print(f"[{'ok' if code == 200 else 'ERR'}] 更新仓库描述: {code}")
    if args.topics:
        topics = [t.strip() for t in args.topics.split(",") if t.strip()]
        code, _r = api("PUT", f"/repos/{owner}/{args.repo}/topics", token,
                       {"names": topics})
        print(f"[{'ok' if code in (200, 201) else 'ERR'}] 设置 {len(topics)} 个 topics: {code}")

    code, ref = api("GET",
                    f"/repos/{owner}/{args.repo}/git/ref/heads/{args.branch}", token)
    base_sha = ref.get("object", {}).get("sha") if code == 200 else None

    if not base_sha:  # 空仓库引导：用 Contents API 建立分支
        b64 = base64.b64encode(b"# bootstrap\n").decode()
        api("PUT", f"/repos/{owner}/{args.repo}/contents/.gitkeep", token,
            {"message": "bootstrap", "content": b64, "branch": args.branch})
        code, ref = api("GET",
                        f"/repos/{owner}/{args.repo}/git/ref/heads/{args.branch}",
                        token)
        base_sha = ref.get("object", {}).get("sha")
        if not base_sha:
            print("[ERR] 空仓库引导失败")
            sys.exit(5)
        print("[ok] 空仓库引导完成")

    # base_tree 要的是 **tree SHA**，不是 commit SHA
    # 传错会偶发 422 GitRPC::BadObjectState
    base_commit = base_sha
    base_tree = None
    if base_commit:
        code, c = api("GET",
                      f"/repos/{owner}/{args.repo}/git/commits/{base_commit}",
                      token)
        if code == 200:
            base_tree = c.get("tree", {}).get("sha")
        else:
            print(f"[WARN] 读取 commit 失败 code={code}，将创建全新 tree")
    print(f"[info] 远程 HEAD commit={(base_commit or '')[:8] or '无'} "
          f"tree={(base_tree or '')[:8] or '空仓库'}")

    files = tracked_files(repo_dir)
    missing = [f for f in files
               if not os.path.isfile(os.path.join(repo_dir, f))]
    if missing:
        print("[ERR] 以下被跟踪文件在磁盘上找不到，中止推送（避免静默漏文件）：")
        for f in missing:
            print("   -", repr(f))
        sys.exit(12)

    total = 0
    print(f"[info] 待推送文件 {len(files)} 个：")
    for rel in files:
        full = os.path.join(repo_dir, rel)
        size = os.path.getsize(full)
        total += size
        print(f"        {size:>10,}  {rel}")
    print(f"[info] 合计 {total/1024/1024:.2f} MB")

    hard, soft = check_risky(files, args.allow_binary)
    if hard:
        print("[ERR] 检测到疑似密钥/私密数据，已中止（不可放行）：")
        for f in hard:
            print("   -", f)
        print("      请把上述文件加入 .gitignore 或移出仓库后重试。")
        sys.exit(11)
    if soft:
        print("[ERR] 检测到二进制文件，已中止：")
        for f in soft:
            print("   -", f)
        print("      建议改走 Release 附件分发（--asset）；"
              "确需提交请显式加 --allow-binary。")
        sys.exit(11)
    print("[ok] 敏感文件闸门通过")

    blobs = []
    for rel in files:
        full = os.path.join(repo_dir, rel)
        if not os.path.isfile(full):
            continue
        with open(full, "rb") as f:
            data = f.read()
        b64 = base64.b64encode(data).decode()
        code, resp = api("POST", f"/repos/{owner}/{args.repo}/git/blobs", token,
                         {"content": b64, "encoding": "base64"})
        if code not in (200, 201):
            print(f"[ERR] blob 失败 {rel}: {code} {resp}")
            sys.exit(6)
        blobs.append({"path": rel.replace("\\", "/"), "mode": "100644",
                      "type": "blob", "sha": resp["sha"]})
    print(f"[ok] 已创建 {len(blobs)} 个 blob")

    # 清理空仓库引导留下的占位文件：必须「远程确实存在」才发删除项
    # （对不存在的路径传 sha=None 会让 GitHub 返回 422 BadObjectState）
    tree_items = list(blobs)
    if base_tree and not os.path.exists(os.path.join(repo_dir, ".gitkeep")):
        code, _ph = api("GET",
                        f"/repos/{owner}/{args.repo}/contents/.gitkeep"
                        f"?ref={args.branch}", token)
        if code == 200:
            tree_items.append({"path": ".gitkeep", "mode": "100644",
                               "type": "blob", "sha": None})
            print("[info] 远程存在占位文件 .gitkeep，将在本次提交中删除")

    tree_payload = {"tree": tree_items}
    if base_tree:
        tree_payload["base_tree"] = base_tree
    code, tree = api("POST", f"/repos/{owner}/{args.repo}/git/trees", token,
                     tree_payload)
    if code not in (200, 201):
        print("[ERR] tree 失败:", code, tree)
        sys.exit(7)
    print("[ok] 已创建 tree")

    code, commit = api("POST", f"/repos/{owner}/{args.repo}/git/commits", token,
                       {"message": args.message, "tree": tree["sha"],
                        "parents": [base_commit] if base_commit else []})
    if code not in (200, 201):
        print("[ERR] commit 失败:", code, commit)
        sys.exit(8)
    print(f"[ok] 已创建 commit {commit['sha'][:8]}")

    code, _ = api("PATCH",
                  f"/repos/{owner}/{args.repo}/git/refs/heads/{args.branch}",
                  token, {"sha": commit["sha"]})
    if code not in (200, 201):  # ref 不存在则创建
        code, _ = api("POST", f"/repos/{owner}/{args.repo}/git/refs", token,
                      {"ref": f"refs/heads/{args.branch}", "sha": commit["sha"]})
    if code not in (200, 201):
        print("[ERR] ref 更新失败:", code)
        sys.exit(9)
    print(f"[ok] 已更新分支 {args.branch}")

    if args.release:
        body = args.release_body
        if args.release_body_file and os.path.isfile(args.release_body_file):
            with open(args.release_body_file, encoding="utf-8") as f:
                body = f.read()
        # 幂等：Release / tag 已存在则复用，不报错
        code, existing = api(
            "GET", f"/repos/{owner}/{args.repo}/releases/tags/{args.release}",
            token)
        if code == 200:
            rid = existing.get("id")
            print(f"[info] Release {args.release} 已存在，复用 (id={rid})")
        else:
            code, rel = api("POST", f"/repos/{owner}/{args.repo}/releases", token,
                            {"tag_name": args.release, "name": args.release,
                             "body": body or args.message,
                             "draft": False, "prerelease": False})
            if code not in (200, 201):
                print("[ERR] release 失败:", code, rel)
                sys.exit(10)
            rid = rel.get("id")
            print(f"[ok] 已创建 Release {args.release} (id={rid})")

        code, assets = api(
            "GET", f"/repos/{owner}/{args.repo}/releases/{rid}/assets", token)
        uploaded = {a["name"] for a in assets} if isinstance(assets, list) else set()

        for asset in args.asset:
            if not os.path.isfile(asset):
                print(f"[WARN] 附件不存在，跳过: {asset}")
                continue
            name = os.path.basename(asset)  # 附件名务必 ASCII，中文会丢失
            if name in uploaded:
                print(f"[info] 附件已存在，跳过: {name}")
                continue
            with open(asset, "rb") as f:
                data = f.read()
            code, aresp = api(
                "POST",
                f"/repos/{owner}/{args.repo}/releases/{rid}/assets"
                f"?name={urllib.parse.quote(name)}",
                token, data, base=UPLOAD)
            if code in (200, 201):
                print(f"[ok] 已上传附件 {name} ({len(data)/1024/1024:.2f} MB)")
            else:
                print(f"[ERR] 附件上传失败 {name}: {code} {aresp}")

    if not args.no_verify:
        verify(owner, args.repo, args.branch, repo_dir, token)

    print("DONE")


if __name__ == "__main__":
    main()
