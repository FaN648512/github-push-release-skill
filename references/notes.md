# GitHub Push 工作流 · 踩坑笔记

## 为什么不能用 git push
沙箱环境内 `github.com:443`（Git 智能 HTTP 端口）被封，curl 探 `git/git.git/info/refs` 超时；
但 `api.github.com:443` 与 `uploads.github.com:443` 可达。因此改走 REST API。

## token 读取
- 本机 Windows 凭据管理器已缓存 `github.com` 条目（账号如 `FaN648512`，含 `repo` 权限）。
- 用 `git -c credential.helper=wincred credential fill` 读取，仅内存使用，不落盘。
- 不要用 `helper-selector`（非交互下随机返回空）。

## 空仓库引导（必做）
新建仓库是空的，Git Data API 建 blob 会 409 "Repository is empty"。
先 `PUT /repos/{o}/{r}/contents/.gitkeep` 提交占位，建立 `main` 分支后再推。

## 附件名
上传时中文会丢失（如 `源码包` -> 孤立下划线）。统一 ASCII：`AudioTranscriber_v1.0.0_source.zip`。

## 验证
- README 公开可访问：可用 `WebFetch https://raw.githubusercontent.com/{o}/{r}/main/README.md` 确认。
- **核验文件树/删除结果（如清 .gitkeep）务必用 `curl` 直连 API**，不要用 WebFetch：
  WebFetch 有约 15 分钟结果缓存，会返回*旧*的 tree（例如仍含已删除的 `.gitkeep`），
  导致误判删除失败。正确做法：
  `curl -sS "https://api.github.com/repos/{o}/{r}/git/trees/main?recursive=1"` 看最新 tree。

## 沙箱清理
临时脚本放在项目目录外（如系统临时目录 `_*.py`），
用完即删；不要留在仓库里。
