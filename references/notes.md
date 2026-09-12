# GitHub Push 工作流 · 踩坑笔记

> 本文件记录推送引擎（`scripts/push_repo.py`）在真实项目中踩过的坑与对应修法。
> 修改脚本前请先读这里，避免把已修的 bug 改回去。

---

## 一、为什么不能用 git push

沙箱环境内 `github.com:443`（Git 智能 HTTP 端口）被封，curl 探
`git/git.git/info/refs` 超时；但 `api.github.com:443` 与
`uploads.github.com:443` 可达。因此改走 REST API。

---

## 二、token 读取

- 本机 Windows 凭据管理器已缓存 `github.com` 条目（账号如 `FaN648512`，含 `repo` 权限）。
- 用 `git credential fill` 读取，仅内存使用，不落盘。
- 给 subprocess 传 `env={**os.environ, "GIT_TERMINAL_PROMPT": "0"}`，避免无 tty 时 git 尝试终端提示。

### ⚠️ 2.1 「Select a credential helper」弹窗 —— 这是"凭据读取偶发超时"的真因

**症状**：每次需要凭据的 git 操作（包括推送脚本）都弹出一个图形窗口
「CredentialHelperSelector · Select a credential helper」，列出
`<no helper>` / `manager` / `wincred` 让你选。人在电脑前点掉才继续；
人不在就**一直卡着直到 subprocess 超时** —— 早期误判为"网络慢 / 凭据读取偶发超时"，
其实是弹窗在等人工点击。

**根因**：`credential.helper` 是**多值**配置，两个层级各写了一条，叠加成列表：

| 层级 | 文件 | 值 |
|------|------|-----|
| system | `PortableGit/versions/<v>/etc/gitconfig` | `helper-selector` |
| global | `~/.gitconfig` | `!"<...>/git-credential-manager.exe"` |

列表 = `[helper-selector, GCM]`。`helper-selector` 是 GCM 的多 helper 选择器，
一旦发现可选 helper 不止一个，就弹窗询问。

**为什么勾「Always use this from now on」不管用**：它会写下
`credential.helperselector.selected = manager`，但真实 helper 配置里写的是
**完整路径** `!"D:/.../git-credential-manager.exe"`，两者名字对不上，
selector 下次仍无法确认，于是继续弹。

**根治（改用户级 ~/.gitconfig，不要动 PortableGit 的 system 配置）**：
git 的官方语义是——**把 `credential.helper` 设为空字符串会清空之前的 helper 列表**。
利用这一点把 system 那条 `helper-selector` 顶掉：

```bash
# 1) 备份
cp ~/.gitconfig ~/.gitconfig.bak_$(date +%Y%m%d)

# 2) 清掉 global 原有项 → 写入空值（重置点）→ 只留一个真实 helper
git config --global --unset-all credential.helper
git config --global --add credential.helper ""
git config --global --add credential.helper \
  '!"D:/.workbuddy/binaries/PortableGit/versions/1.2.0/mingw64/bin/git-credential-manager.exe"'

# 3) 核对：global 应出现「空行 + 一条路径」
git config --show-origin --get-all credential.helper
```

**验证**：跑一次带超时的 `git credential fill`，**应在 5 秒内返回**（实测修复后 0.5 秒，
修复前会卡到超时）。凭据仍能正常读到 `username=FaN648512` + 40 字符 token。

**脚本侧的双保险（必做）**：`-c credential.helper=X` 只是**追加**到列表末尾、**不清空**
原有项 —— 所以单靠它摘不掉 system 的 selector。正确写法是两个 `-c`：

```python
["git",
 "-c", "credential.helper=",            # 先清空（摘掉 system 的 helper-selector）
 "-c", f"credential.helper={helper}",   # 再指定唯一 helper
 "credential", "fill"]
```

这样即使 ~/.gitconfig 被重装/升级重置，脚本自身也不会弹窗。

---

## 三、⚠️ 中文文件名会被静默丢弃（最危险，必看）

**现象**：日志打印"待推送文件 23 个"，实际只推上去 9 个，且**不报任何错**。

**根因**：git 默认 `core.quotepath=true`，会把非 ASCII 路径转义成八进制字符串：

```
使用说明.html   →   "\344\275\277\347\224\250\350\257\264\346\230\216.html"
```

脚本拿这个转义串去 `os.path.isfile()` 自然判定失败，于是 `continue` 跳过，
文件就这么无声无息地丢了。

**修法**（三重保险，缺一不可）：

1. `git -c core.quotepath=false ls-files -z` —— 关闭转义 + 用 NUL 分隔，
   同时避免路径含空格/引号/换行带来的解析歧义；
2. 字节流用 UTF-8 显式解码，不要依赖 locale 默认编码；
3. **推送前做"文件必须存在"硬断言**：任何被跟踪文件在磁盘上找不到就 `sys.exit(12)` 中止，
   绝不允许 `continue` 静默跳过。

**验证方法**：推送后对比"本地文件数"与"远程 tree 的 blob 数"，两者必须相等。

---

## 四、base_tree 要的是 tree SHA，不是 commit SHA

`POST /git/trees` 的 `base_tree` 字段需要 **tree SHA**；传 commit SHA 时会偶发
`422 GitRPC::BadObjectState`——前两次侥幸成功、第三次必现，极难定位。

**修法**：先 `GET /git/commits/{sha}` 取出 `.tree.sha` 再用：

```python
code, c = api("GET", f"/repos/{owner}/{repo}/git/commits/{base_commit}", token)
base_tree = c["tree"]["sha"] if code == 200 else None
```

`POST /git/commits` 的 `parents` 字段则相反，要的是 **commit SHA**——两个字段别搞混。

---

## 五、删除不存在的路径也会 422

想清理空仓库引导留下的 `.gitkeep`，会在 tree 里放一条 `{"path": ".gitkeep", "sha": None}`。
如果这个文件**远程已经不存在**了，GitHub 仍会返回 `422 BadObjectState`。

**修法**：先 `GET /contents/.gitkeep?ref=<branch>`，只有返回 200（确认远程存在）
才把删除项加进 tree。

---

## 六、空仓库引导（必做）

新建仓库是空的，往空仓库建 blob 会 `409 Repository is empty`。
必须先 `PUT /repos/{o}/{r}/contents/.gitkeep` 提交占位，建立分支后再推代码；
推完真实文件后再按上文第五条把占位删掉。

---

## 七、换行符：本地 / 远程 / 本地 git 三者不一致

**现象**：核验时发现本地 git blob sha 与远程 blob sha 对不上，但文件内容肉眼看一样。

**根因**：文件在磁盘上是 CRLF，而 `.gitattributes` 写了 `* text=auto eol=lf`，
**本地 git 入库时把 CRLF 规范化成了 LF**（所以本地 sha 是 LF 版），
而脚本是**按磁盘原始字节**（CRLF 版）上传的，两者 sha 必然不同。

**修法**：统一磁盘文件为 LF 再推。

```python
data = open(p, "rb").read().replace(b"\r\n", b"\n")
open(p, "wb").write(data)
```

配合 `.gitattributes` 里 `* text=auto eol=lf`（`.bat` 除外，它必须是 CRLF）。
核验时若只剩个别文件哈希不同，**优先怀疑换行符**，而不是文件真丢了。

---

## 八、附件名

上传时中文会丢失（如 `源码包` → 孤立下划线）。统一 ASCII：
`ScreenOff-portable-v1.0.0.zip`、`AudioTranscriber_v1.0.0_source.zip`。

---

## 九、验证

- README 公开可访问：可用 `WebFetch https://raw.githubusercontent.com/{o}/{r}/main/README.md` 确认。
- **核验文件树 / 删除结果（如清 .gitkeep）务必直连 API**，不要用 WebFetch：
  WebFetch 有约 15 分钟结果缓存，会返回*旧*的 tree（例如仍含已删除的 `.gitkeep`），
  导致误判。正确做法是用 Python `urllib` 或 `curl` 直连：
  `GET https://api.github.com/repos/{o}/{r}/git/trees/{branch}?recursive=1`
- **用 `--verify`（默认开启）自动核验**：脚本推送后会自动比对本地 git blob sha
  与远程 tree 的 blob sha，逐文件报告"一致 / 仅本地 / 仅远程 / 哈希不同"。
- 若需刷新 README 在网页上的渲染，需等 CDN 缓存过期，或加 `?v=<时间戳>` 强刷。

---

## 十、网络抖动

`raw.githubusercontent.com` 偶发 `WinError 10054 远程主机强迫关闭了一个现有的连接`。
拉取仓库文件时**优先走 `api.github.com/repos/.../contents/{path}`**（配合
`Accept: application/vnd.github.raw`），比 raw 域名稳定；并加重试循环。

---

## 十一、沙箱清理

临时脚本放在项目目录外（如系统临时目录 `_*.py`），用完即删；不要留在仓库里。
