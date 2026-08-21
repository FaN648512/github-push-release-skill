#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通过 GitHub REST API 将本地项目推送到 GitHub。

适用场景：沙箱环境 github.com:443 的 Git 协议端口被封，无法 git push。
改走 GitHub Git Data / Contents / Releases REST API 完成等效推送。

用法：
  python push_repo.py --repo <仓库名> [--path <目录>] [--private]
                      [--release <v1.0.0>] [--asset <附件路径>]
                      [--message <提交说明>] [--branch main]
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


def get_token():
    """从 Windows 凭据管理器 (wincred) 读取 GitHub token，不落盘。"""
    for helper in ("wincred", "manager-core", "manager", ""):
        args = (["git", "credential", "fill"] if not helper
                else ["git", "-c", f"credential.helper={helper}",
                      "credential", "fill"])
        try:
            p = subprocess.run(args,
                               input="protocol=https\nhost=github.com\n",
                               capture_output=True, text=True, timeout=30)
        except Exception:
            continue
        for line in p.stdout.splitlines():
            if line.startswith("password="):
                return line[len("password="):]
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
        with urllib.request.urlopen(req, timeout=60) as r:
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
    """git add -A 后列出被跟踪文件（自动尊重 .gitignore）。"""
    subprocess.run(["git", "add", "-A"], cwd=repo_dir, capture_output=True)
    out = subprocess.run(["git", "ls-files"], cwd=repo_dir,
                         capture_output=True, text=True)
    return [l for l in out.stdout.splitlines() if l.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--path", default=os.getcwd())
    ap.add_argument("--private", action="store_true")
    ap.add_argument("--release", default=None, help="版本标签 e.g. v1.0.0")
    ap.add_argument("--asset", default=None, help="要上传的附件路径")
    ap.add_argument("--message", default="Update via github-push-release")
    ap.add_argument("--branch", default="main")
    args = ap.parse_args()

    token = get_token()
    if not token:
        print("[ERR] 未在本机凭据管理器找到 GitHub token（wincred）。", file=sys.stderr)
        sys.exit(2)
    print("[ok] 已读取 GitHub token")

    code, me = api("GET", "/user", token)
    if code != 200:
        print("[ERR] 获取用户信息失败:", code, me)
        sys.exit(3)
    owner = me["login"]
    print(f"[ok] 登录账号: {owner}")

    repo_dir = os.path.abspath(args.path)

    if not os.path.isdir(os.path.join(repo_dir, ".git")):
        subprocess.run(["git", "init"], cwd=repo_dir, capture_output=True)
        subprocess.run(["git", "checkout", "-b", args.branch],
                       cwd=repo_dir, capture_output=True)
        print("[ok] 已 git init")

    code, _ = api("GET", f"/repos/{owner}/{args.repo}", token)
    if code == 404:
        code, resp = api("POST", "/user/repos", token, {
            "name": args.repo, "private": args.private,
            "auto_init": False, "description": "Pushed via github-push-release"})
        if code not in (200, 201):
            print("[ERR] 创建仓库失败:", code, resp)
            sys.exit(4)
        print(f"[ok] 已创建仓库 {owner}/{args.repo}")
    elif code == 200:
        print(f"[ok] 仓库已存在 {owner}/{args.repo}")
    else:
        print("[ERR] 检查仓库失败:", code)
        sys.exit(4)

    code, ref = api("GET",
                    f"/repos/{owner}/{args.repo}/git/ref/heads/{args.branch}", token)
    base_sha = ref.get("object", {}).get("sha") if code == 200 else None

    if not base_sha:  # 空仓库引导：用 Contents API 建立 main 分支
        ph = "# placeholder\n"
        b64 = base64.b64encode(ph.encode()).decode()
        api("PUT", f"/repos/{owner}/{args.repo}/contents/.gitkeep", token,
            {"message": "bootstrap", "content": b64, "branch": args.branch})
        code, ref = api("GET",
                        f"/repos/{owner}/{args.repo}/git/ref/heads/{args.branch}", token)
        base_sha = ref.get("object", {}).get("sha")
        if not base_sha:
            print("[ERR] 空仓库引导失败")
            sys.exit(5)
        print("[ok] 空仓库引导完成")

    files = tracked_files(repo_dir)
    print(f"[info] 待推送文件: {len(files)}")

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
        blobs.append({"path": rel, "mode": "100644",
                      "type": "blob", "sha": resp["sha"]})
    print(f"[ok] 已创建 {len(blobs)} 个 blob")

    code, tree = api("POST", f"/repos/{owner}/{args.repo}/git/trees", token,
                     {"base_tree": base_sha, "tree": blobs})
    if code not in (200, 201):
        print("[ERR] tree 失败:", code, tree)
        sys.exit(7)
    print("[ok] 已创建 tree")

    code, commit = api("POST", f"/repos/{owner}/{args.repo}/git/commits", token,
                       {"message": args.message, "tree": tree["sha"],
                        "parents": [base_sha]})
    if code not in (200, 201):
        print("[ERR] commit 失败:", code, commit)
        sys.exit(8)
    print("[ok] 已创建 commit")

    code, _ = api("PATCH",
                  f"/repos/{owner}/{args.repo}/git/refs/heads/{args.branch}",
                  token, {"sha": commit["sha"]})
    if code not in (200, 201):  # ref 不存在则创建
        code, _ = api("POST", f"/repos/{owner}/{args.repo}/git/refs", token,
                      {"ref": f"refs/heads/{args.branch}", "sha": commit["sha"]})
    if code not in (200, 201):
        print("[ERR] ref 更新失败:", code)
        sys.exit(9)
    print(f"[ok] 已更新 {args.branch}")

    if args.release:
        code, rel = api("POST", f"/repos/{owner}/{args.repo}/releases", token,
                        {"tag_name": args.release, "name": args.release,
                         "body": args.message, "draft": False, "prerelease": False})
        if code not in (200, 201):
            print("[ERR] release 失败:", code, rel)
        else:
            rid = rel.get("id")
            print(f"[ok] 已创建 Release {args.release} (id={rid})")
            if args.asset and os.path.isfile(args.asset):
                name = os.path.basename(args.asset)
                with open(args.asset, "rb") as f:
                    data = f.read()
                code, aresp = api(
                    "POST",
                    f"/repos/{owner}/{args.repo}/releases/{rid}/assets"
                    f"?name={urllib.parse.quote(name)}",
                    token, data, base=UPLOAD)
                if code not in (200, 201):
                    print("[ERR] 附件上传失败:", code, aresp)
                else:
                    print(f"[ok] 已上传附件 {name}")
    print("DONE")


if __name__ == "__main__":
    main()
