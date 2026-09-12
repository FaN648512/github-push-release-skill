# github-push-release

> 一站式 GitHub 仓库工作流技能：研究同类案例 → 优化 README → 推送同步。
> 在沙箱环境（github.com:443 的 Git 协议端口被封）下，通过 GitHub REST API 完成建仓库、推代码、发版、传附件。

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-agnostic-green.svg)](https://github.com)
[![Auth](https://img.shields.io/badge/auth-wincred--auto-green.svg)](https://github.com)
[![Workflow](https://img.shields.io/badge/workflow-research%20%E2%86%92%20README%20%E2%86%92%20push-orange.svg)](https://github.com)
[![Python](https://img.shields.io/badge/python-3.x%20stdlib%20only-blue.svg)](https://github.com)
[![Verified](https://img.shields.io/badge/consistency-verified-brightgreen.svg)](https://github.com)

---

## 这是什么

`github-push-release` 是一个 **与平台无关的通用技能（Skill）**，把"调研 → 写作 → 发布"三步串成一条可复用指令，让智能体（Agent）在任意项目上一句话完成：

1. **研究案例**：联网调研同类标杆产品，提炼其*核心优势、特色亮点、UI 审美设计风格*，归纳本项目的差异化定位。
2. **优化 README**：基于研究成果，按最佳实践结构重写仓库自述文件，提升可读性、专业性与吸引力。
3. **推送同步**：把结果（代码 / README）自动推送到 GitHub，可选发布 Release 与上传附件，并做公开可访问验证。

---

## 核心优势

| 维度 | 说明 |
|------|------|
| **零明文凭据** | 自动从 Windows 凭据管理器（`wincred`）读取 GitHub token，全程不落盘，无需手动粘贴 PAT |
| **绕过沙箱封锁** | 当 `github.com:443` 的 Git 协议端口不可用时，自动改用 GitHub Git Data / Contents / Releases REST API 完成等效推送 |
| **中文路径安全** | 关闭 `core.quotepath` 并用 `-z` 取文件列表，配合"文件必须存在"硬断言，杜绝中文名文件被**静默丢弃** |
| **推送后自动核验** | 逐文件比对本地 git blob sha 与远程 tree 的 blob sha，直接给出「一致 / 仅本地 / 仅远程 / 哈希不同」结论 |
| **敏感文件闸门** | 命中 `.env` / `token` / `password` / `id_rsa` / `.pem` / `.workbuddy` 一律中止；`.exe` / `.zip` 等二进制需 `--allow-binary` 显式放行 |
| **空仓库引导** | 新建仓库无法直接建 blob（409），自动用 Contents API 建立 `main` 分支，推完再清掉占位文件 |
| **幂等发布** | Release 已存在则复用，附件已上传则跳过，重复执行不报错 |
| **附件名 ASCII 化** | Release 附件名统一 ASCII，规避中文名在 `uploads.github.com` 上传时丢失的问题 |
| **可复用工作流** | 封装为 Skill 后，对任意项目一句话即可触发，内置全部踩坑经验 |

---

## 目录结构

```
github-push-release/
├── SKILL.md            # 技能定义与三阶段编排（含触发词、用法、边界）
├── README.md           # 本文件
├── scripts/
│   └── push_repo.py    # 推送引擎（GitHub REST API，绕过 git 端口封锁）
└── references/
    ├── readme-guide.md # 竞品研究方法 + README 最佳结构模板 + UI 审美落地方向
    └── notes.md        # 全部踩坑笔记（改脚本前必读）
```

---

## 安装（通用：兼容所有支持 SKILL.md 的智能体）

> **本技能与平台无关（agent-agnostic）。** 它是纯文本的「SKILL.md + references/ + scripts/」结构，不依赖任何平台专有 API；推送引擎仅用 Python 标准库与 GitHub REST API，可在任意支持「读取 SKILL.md 作为指令」的智能体中使用。下面给出通用安装步骤与主流智能体的路径规范。

### 1. 获取 skill 文件

任选一种：

- **方式 A · Git 克隆（推荐，便于更新）**
  ```bash
  git clone https://github.com/FaN648512/github-push-release.git
  ```
- **方式 B · 下载压缩包**：在仓库页面点击 `Code → Download ZIP`，解压后得到 `github-push-release/` 文件夹。
- **方式 C · 手动复制**：直接复制整个 `github-push-release/` 目录到本地任意位置。

无论哪种方式，请**保持目录内相对结构**不变：

```
github-push-release/
├── SKILL.md            # 技能定义与三阶段编排（含触发词、用法、边界）
├── README.md           # 本文件
├── scripts/
│   └── push_repo.py    # 推送引擎（GitHub REST API，仅 Python 标准库）
└── references/
    ├── readme-guide.md # 竞品研究方法 + README 最佳结构模板
    └── notes.md        # 全部踩坑笔记
```

### 2. 放置到对应智能体的 skills 目录（路径规范）

**通用放置原则**：把整个 `github-push-release/` 文件夹放进你的智能体的 **skills 目录**（**文件夹名即 skill 名，必须一致**），即 `.../skills/github-push-release/`。常见智能体的 skills 目录约定如下（「用户级」对当前用户所有项目生效，最常用；「项目级」仅对该项目生效）：

| 智能体 (agent) | 用户级路径 | 项目级路径（仓库内） | 类型 |
|---------------|-----------|---------------------|------|
| **Claude Code / Claude Desktop**（Anthropic） | `~/.claude/skills/github-push-release/` | `<项目>/.claude/skills/github-push-release/` | 官方支持 |
| **Cline**（开源） | `~/.cline/skills/github-push-release/` | `<项目>/.cline/skills/github-push-release/` | 社区约定 |
| **Codex CLI**（OpenAI） | `~/.codex/skills/github-push-release/` | `<项目>/.codex/skills/github-push-release/` | 社区约定（实验性） |

> 你的智能体未在表中列出？没关系——**放置原则是通用的**：找到该智能体读取 skill 的目录（通常叫 `skills`，或其文档中的 "skills directory"），把整个文件夹放进去即可；若它没有 skills 目录，走下方「通用兜底方案」。

> **Windows 路径对应**：用户级 `~` 即 `C:\Users\<你的用户名>\`。例：`C:\Users\<用户名>\.claude\skills\github-push-release\`。
> **macOS / Linux 路径**：`~` 即 `/Users/<用户名>/` 或 `/home/<用户名>/`。

**通用兜底方案（任意智能体都可用）**：若你的智能体没有 skills 目录（如 Cursor，或纯系统提示场景），把 `SKILL.md` 正文与 `references/` 下的指南内容合并进该智能体的 `AGENTS.md` / `CLAUDE.md` / `.cursorrules` / 系统提示（System Prompt）。效果等价，无需目录约定。

### 3. 导入 / 启用操作

把 skill 放入目录后，**无需任何额外配置**即可使用。常见的启用方式：

- **支持 skill 自动触发的智能体**（如 Claude Code / Desktop）：放好后用 `/skills` 可看到该 skill；对话里说「研究优秀案例并重写自述文件，然后把 audio-transcriber 推到 GitHub」即可自动触发。
- **通过命令行加载的智能体**（如 Cline / Codex CLI）：放入对应 `skills/` 目录后，重启会话，在对话中引用 skill 名触发。
- **无 skills 目录的智能体**：走上方「通用兜底方案」，把内容写入其每次自动加载的说明文件后，直接说「研究案例并优化 README 后推到 GitHub」即可。

> 若智能体**不支持 skill 自动触发**，只需在提问时显式带上 skill 名，例如：「请用 github-push-release 的方法，研究案例、优化 README 并推送到 GitHub」——这条对任何智能体都适用。

### 4. 导入后的验证方法

1. **列表验证**：在智能体中执行 `/skills`（或等价命令），确认 `github-push-release` 出现在技能列表。
2. **功能性验证（推荐）**：发起一次真实任务，例如：
   > 「研究优秀案例并重写自述文件，然后把 <某个项目> 推到 GitHub」
   正确加载时，你会看到它按三阶段推进：① 联网研究同类标杆；② 优化 README；③ 调用 `scripts/push_repo.py` 推送并验证公开可访问。
3. **路径验证**：确认 `<skills 目录>/github-push-release/scripts/push_repo.py` 与 `references/readme-guide.md` 存在且可读——推送与 README 研究都依赖它们。

### 前置条件（功能依赖，非平台依赖）

- **Python 3**：推送引擎仅用标准库（`argparse` / `urllib` / `subprocess` / `base64`），无需第三方包。
- **GitHub 凭据**：运行环境需在 Windows 凭据管理器已缓存 `github.com` 条目（需 `repo` 写权限）；若未缓存，脚本会报错退出，此时需手动提供 PAT（仅本次内存使用，不落盘）。
- **网络**：需能访问 `api.github.com` 与 `uploads.github.com`（端口 443）。若 `github.com` 的 Git 协议端口被封，本技能会自动改用 REST API 完成等效推送。

---

## 用法

### 方式 A：作为技能一键触发

在任何智能体对话中说，例如：

> "研究优秀案例并重写自述文件，然后把 audio-transcriber 推到 GitHub"

Agent 会按 `SKILL.md` 的三阶段自动推进。

### 方式 B：直接调用推送引擎

`scripts/push_repo.py` 是纯标准库 Python，可独立运行：

```bash
python scripts/push_repo.py \
  --repo <仓库名> \
  --path <项目目录> \
  [--private] \
  [--release v1.0.0] \
  [--asset <附件1>] [--asset <附件2>] ... \
  [--release-body-file <md 文件>] \
  [--description "仓库描述"] [--topics a,b,c] \
  [--message "提交说明"] \
  [--branch main] \
  [--allow-binary] [--no-verify]
```

| 参数 | 作用 |
|------|------|
| `--repo` / `--path` | 仓库名 / 项目目录（默认当前目录） |
| `--private` | 建为私有仓库（默认公开） |
| `--description` / `--topics` | 设置仓库描述、topics（逗号分隔） |
| `--release` | 版本标签，如 `v1.0.0`；已存在则复用（幂等） |
| `--asset` | Release 附件，**可重复传入多个**；建议 ASCII 命名 |
| `--release-body` / `--release-body-file` | Release 说明正文 / 从 UTF-8 文件读取（长中文建议用文件） |
| `--message` | 提交说明 |
| `--allow-binary` | 允许提交 `.exe` / `.zip` 等二进制（默认中止） |
| `--no-verify` | 跳过推送后的一致性核验（默认开启核验） |

示例：

```bash
# 新建公开仓库并推送当前目录代码
python scripts/push_repo.py --repo my-project --path .

# 推送并发布 v1.0.0 Release，附带多个附件 + 设置 topics
python scripts/push_repo.py --repo my-project --path . \
  --release v1.0.0 \
  --asset dist/my-project.zip --asset dist/my-project.exe \
  --description "一句话说清这是什么" \
  --topics windows,cli,utility \
  --message "feat: v1.0.0 首发"
```

---

## 工作原理

核心是**用 Git Data API 手工走一遍 `git push` 的等价流程**：

```mermaid
flowchart LR
    A["读取 wincred token"] --> B{"仓库存在?"}
    B -- 否 --> C["POST /user/repos<br/>建仓库 + 描述 + topics"]
    B -- 是 --> D{"分支存在?"}
    C --> D
    D -- 否 --> E["PUT /contents/.gitkeep<br/>空仓库引导"]
    D -- 是 --> F["GET /git/commits/{sha}<br/>取 tree SHA"]
    E --> F
    F --> G["敏感闸门<br/>密钥/二进制检查"]
    G --> H["POST /git/blobs<br/>逐文件上传"]
    H --> I["POST /git/trees<br/>base_tree=tree SHA"]
    I --> J["POST /git/commits"]
    J --> K["PATCH /git/refs/heads/main"]
    K --> L["可选：发布 Release<br/>上传附件"]
    L --> M["核验：本地 blob sha<br/>vs 远程 tree sha"]
```

---

## 常见问题

<details>
<summary><b>推送日志说"待推送 23 个"，但远程只有 9 个文件？</b></summary>

中文文件名被静默丢弃了。git 默认会把中文路径转义成 `\344\275\277...`，
按这个转义串去读文件必然失败。本脚本已用
`git -c core.quotepath=false ls-files -z` 修复，并加了"文件必须存在就中止"的硬断言。
详见 `references/notes.md` 第三条。
</details>

<details>
<summary><b>报 <code>422 GitRPC::BadObjectState</code>？</b></summary>

两种原因，脚本均已内置修法：
① `base_tree` 传成了 commit SHA（应传 tree SHA）；
② 在 tree 里删除一个**远程已不存在**的路径（如已被清掉的 `.gitkeep`）。
</details>

<details>
<summary><b>核验显示个别文件"哈希不同"，但内容看起来一样？</b></summary>

几乎一定是换行符问题。文件在磁盘上是 CRLF，而 `.gitattributes` 声明了
`* text=auto eol=lf`——本地 git 入库时规范化成了 LF，而脚本按磁盘原始字节上传。
把磁盘文件统一为 LF 再推即可。详见 `references/notes.md` 第七条。
</details>

<details>
<summary><b>附件上传后名字变成孤立下划线？</b></summary>

`uploads.github.com` 对非 ASCII 附件名支持不佳，统一用 ASCII：
`ScreenOff-portable-v1.0.0.zip` 而不是 `关闭屏幕-绿色版.zip`。
</details>

<details>
<summary><b>WebFetch 查到远程还留着已删除的文件？</b></summary>

WebFetch 有约 15 分钟结果缓存，会返回*旧*的 tree。核验文件树请直连 API：
`GET /repos/{o}/{r}/git/trees/{branch}?recursive=1`。
</details>

<details>
<summary><b><code>git credential fill</code> 卡住不动 / 报找不到凭据？</b></summary>

该命令在无交互环境下偶发长时间阻塞，超时值需给到 90 秒（30 秒会误判成"没凭据"）。
脚本已按 90 秒处理。
</details>

<details>
<summary><b>可以从 <code>raw.githubusercontent.com</code> 拉文件但偶尔连接被重置？</b></summary>

网络抖动（`WinError 10054`）。改用 `api.github.com/repos/.../contents/{path}`
配合 `Accept: application/vnd.github.raw`，比 raw 域名稳定，并加重试。
</details>

---

## 实战验证

本脚本已在真实项目上端到端跑通并留档：

| 项目 | 结果 |
|------|------|
| [`screen-off`](https://github.com/FaN648512/screen-off) | 23 个文件（含 6 个中文名文件）逐字节一致，Release v1.0.0 挂 3 个附件 |
| `github-push-release` 自身 | 用本脚本完成自我更新（含中文文档与 references） |

一致性核验的判定标准：本地 `git ls-files -s` 的 blob SHA 与远程
`GET /git/trees/{branch}?recursive=1` 返回的 blob SHA **全部相等**。

---

## 路线图

- [x] Git Data API 等效推送（blob → tree → commit → ref）
- [x] 空仓库引导 + 占位文件自动清理
- [x] 多附件发布、幂等 Release、topics / description
- [x] 敏感文件闸门 + 中文路径安全 + 推送后自动核验
- [ ] 支持 Git LFS 大文件（当前建议走 Release 附件）
- [ ] 推送前本地 README Markdown lint 检查
- [ ] 可选：推送结果生成 Markdown 报告卡片

---

## 贡献

欢迎 Issue / PR。改动 `scripts/push_repo.py` 前请先读 `references/notes.md`，
那里记录了每一个坑的成因与修法——**不要把已修的 bug 改回去**。

---

## 安全与边界

- 对外写操作（建仓库、推代码、发版）前会确认用户意图；公开发布前再次确认不含密钥。
- 不修改用户其他仓库；不删除远程任何内容。
- 若要求"定时自动推送"，会先明确告知自动推送未经人工 review 的风险，再决定是否配置自动化任务。

---

## License

MIT —— 可自由使用、修改与再分发。
