<p align="center"><a href="README.zh-CN.md">中文</a> | <a href="README.es.md">Español</a> | <a href="README.md">English</a></p>

<div align="center">

<img src="docs/media/ephe-bee-512.png" alt="Ephe — 火灵蜜蜂" width="88">

# Ephe

**Ephe 是一个本地优先的智能体工作台，运行在你自己的机器上——一个瞬时 SI 智能体，通过同一个 Python 后端，你可以在 CLI（`ephe tui`）或桌面应用（`ephe start`）中驱动它。引擎由你选择：本地 Ollama、远程 Ollama，或任何兼容 OpenAI 的端点，没有静默默认。可选的在线/API 功能始终需要显式开启。**

<img src="docs/screenshots/hero-banner.png" alt="Ephe 的聊天工作台：助手阅读面板中嵌套着已完成的工具行，侧边栏是任务列表，输入框位于状态栏上方" width="100%">

一条命令即可安装应用；之后在应用内选择引擎，可以是本地 Ollama、远程 Ollama，或像 DGX Spark 这样兼容 OpenAI 的端点。安装器不会安装 Ollama，也不会拉取模型。在选择引擎之前，应用会明确提示并等待，没有隐藏的回退路径；选择之后，完全离线的本地部署与远程高吞吐部署地位相同。自定义 Ollama 服务器、公网手机访问、联网检索、文本转语音服务以及兼容 OpenAI 的 API 都是可选的显式路径。

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org) [![Engine chosen in-app](https://img.shields.io/badge/Engine-chosen%20in%20app-8250df?style=for-the-badge)](https://ollama.com)
[![License](https://img.shields.io/badge/License-BUSL%201.1-2d6a4f?style=for-the-badge)](LICENSE) [![Tests](https://github.com/bemlerlabs/ephe/actions/workflows/tests.yml/badge.svg)](https://github.com/bemlerlabs/ephe/actions/workflows/tests.yml) [![Frontend Build](https://github.com/bemlerlabs/ephe/actions/workflows/frontend-build.yml/badge.svg)](https://github.com/bemlerlabs/ephe/actions/workflows/frontend-build.yml)
[![Lang-中文](https://img.shields.io/badge/Lang-中文-red?style=for-the-badge)](README.zh-CN.md) [![Lang-Español](https://img.shields.io/badge/Lang-Español-orange?style=for-the-badge)](README.es.md)

</div>

<div align="center">

**你的 Star 能帮助更多人发现 Ephe。**

</div>

<details>
<summary>目录</summary>

- [快速安装](#-快速安装)
- [最初两分钟](#最初两分钟)
- [接下来可以做什么](#接下来可以做什么)
- [Ephe 是什么，不是什么](#ephe-是什么不是什么)
- [桌面外壳](#桌面外壳)
- [获取帮助](#获取帮助)
- [许可证](#许可证)

- [快速上手](docs/QUICKSTART.md) · [概览](docs/AT_A_GLANCE.md) · [功能状态](docs/FEATURE_STATUS.md) · [技能](docs/SKILLS.md) · [插件](docs/PLUGINS_OVERVIEW.md) · [基准测试](docs/BENCHMARKS.md) · [演示](docs/DEMOS.md)
- [安装选项](docs/INSTALL_OPTIONS.md) · [CLI](docs/CLI.md) · [架构](docs/ARCHITECTURE.md) · [开发](docs/DEVELOPMENT.md) · [手机访问](docs/MOBILE.md) · [Telegram](docs/TELEGRAM.md) · [安全与隐私](docs/SECURITY_AND_PRIVACY.md) · [文档索引](docs/README.md)

</details>

## ⚡ 快速安装

使用仓库自带的安装器——这是目前可用且受支持的路径：

```bash
curl -fsSL https://raw.githubusercontent.com/bemlerlabs/ephe/main/install.sh | bash
```

应用尚未公证：在 macOS 上，首次启动会询问一次，你需要在“系统设置 → 隐私与安全性 → 仍要打开”中放行。

包管理器路径（npm 上的 `@ephemora/ephe`、Homebrew cask、Scoop manifest）会在发布流程自动产出后提供；在那之前，上面这条命令是唯一可用的方式。npm 上不带 scope 的同名包属于一个无关项目，因此我们的包带 scope。

这条单行命令从已发布仓库获取 `./install.sh` 并执行。若想在执行前阅读脚本，可以在本地检出中使用同一个脚本：

```bash
git clone https://github.com/bemlerlabs/ephe.git && cd ephe && ./install.sh
```

安装器把文件放在哪里、检查哪些项目、uv 下载如何校验：[docs/INSTALL_OPTIONS.md](docs/INSTALL_OPTIONS.md#what-the-installer-does)。安装步骤、两种选择引擎的方式，以及 API 密钥的实际来源：[docs/FIRST_RUN.md](docs/FIRST_RUN.md)。

### Windows（PowerShell）

```powershell
curl -fsSL https://raw.githubusercontent.com/bemlerlabs/ephe/main/install.ps1 -o install.ps1; powershell -ExecutionPolicy Bypass -File .\install.ps1
powershell -ExecutionPolicy Bypass -File .\install.ps1   # 在本地检出中安装
```

安装模式可选：`--cli`（仅 TUI/Textual，依赖最少）或 `--desktop`/`--gui`（默认，包含 PWA、图形界面与语音）。不带参数时，安装器会交互式询问。

卸载也随检出提供：`./uninstall.sh --dry-run` 只打印计划、不做任何更改；`./uninstall.sh --keep-data` 删除检出但保留 `~/.ephe`。Docker、安装器环境变量与供应链检查见 [docs/INSTALL_OPTIONS.md](docs/INSTALL_OPTIONS.md) 和 [docs/INSTALL.md](docs/INSTALL.md)。

### 系统要求

| 组件 | 最低要求 | 说明 |
|---|---|---|
| 操作系统 | macOS 13+、Ubuntu 22+，或使用 PowerShell 路径的 Windows | 需要现代浏览器 |
| Python | 3.10 或更高版本 | `.python-version` 为本检出固定 3.13 |
| 内存 | 小型本地模型保留 8 GB 可用内存 | 本地 12B 级模型建议 16 GB+；远程端点无需本地内存 |
| 存储 | 12 GB 可用空间 | 建议 20 GB+ |

完整表格见 [docs/INSTALL_OPTIONS.md](docs/INSTALL_OPTIONS.md#system-requirements)。

### 命令地图

```bash
ephe start --open          # 本地 Web 应用 + 浏览器（端口 8765）
ephe tui                   # 终端界面（Textual），使用已配置的引擎
ephe desktop               # 构建 Tauri 外壳，安装到 /Applications 并打开
ephe configure             # 一次性选择引擎（保存到 ~/.ephe/engine.json）
ephe doctor                # 安装检查；`ephe doctor --fix` 执行安全的本地修复
ephe update                # 拉取仓库 + 依赖 + 模型
ephe serve                 # 兼容 OpenAI 的引擎（/v1/chat/completions）
ephe session list|new|switch|rm|rename
```

所有参数、审批门槛与退出码见 [docs/CLI.md](docs/CLI.md)。

## 最初两分钟

从本地检出开始，五步即可进入可用的会话。每个编号步骤是一条命令，下面是编写本节时这台机器实际打印的内容；过长的绝对路径以 `…` 省略。

1. **安装。** `./install.sh` 准备 Python、构建 PWA、在 `~/.ephe/` 下创建数据目录，并在 `http://127.0.0.1:8765` 启动本地服务器。加上 `--dry-run` 可只打印计划、不做任何更改：

   ```text
   ▶ Checking the system
     ✓ Darwin supported
     ✓ Disk space OK
   ▶ Checking Python 3.10+
     ✓ 3.12.15 found
   ▶ Setting up the local Python environment
     DRY-RUN: pnpm --dir …/app install --frozen-lockfile
     DRY-RUN: pnpm --dir …/app run build
     ✓ PWA built → app/dist
   Setup complete.
   ```

   该脚本就是[快速安装](#-快速安装)中的那条单行命令。

2. **一次性选择引擎。** `ephe configure` 把选择保存到 `~/.ephe/engine.json`。在保存之前，应用和 `ephe start` 都会拒绝启动，并给出两种解决方式：

   ```text
   $ ephe start
   Error: No engine configured.
     Fix: Run `ephe configure` and pick your engine (saved to ~/.ephe/engine.json), or set it
     explicitly via env: EPHE_MODEL_PROVIDER=local_ollama|custom_ollama|openai_compatible ...
   ```

3. **检查安装。** `ephe doctor` 为每项检查打印一行，只要有项目缺失就以非零状态退出：

   ```text
   OK      Python - 3.13.5
   OK      Engine openai_compatible - deepseek-v4-pro @ https://api.deepseek.com/v1 — engine up
   OK      Ephe server - http://127.0.0.1:8765
   OK      skills-lock.json - 51 packs match
   MISSING Voice (TTS) - piper not found — setup: 'brew install piper' ...
   Summary: 10/12 checks OK
   ```

4. **启动。** 应用使用 `ephe start --open`，终端使用 `ephe tui`。`ephe start --lan --open` 还会在局域网中暴露服务，便于手机配对。

5. **提问。** 这是应用针对第 2 步保存的引擎发出的调用——下面的请求耗时 4.7 秒：

   ```text
   $ curl -s -X POST http://127.0.0.1:8765/api/chat -H 'Content-Type: application/json' \
       -d '{"message":"Answer in one short sentence: what is 17 * 3?","mode":"ask"}'
   {"response": "17 × 3 is **51**.", "model": "deepseek-v4-pro"}
   ```

截图与短片位于 `docs/screenshots/`（上方的横幅）和 `docs/media/`（[演示](docs/DEMOS.md)中的 WebP 短片）。

## 接下来可以做什么

以下是本产品区别于普通聊天窗口的五件事。

1. **选择引擎，并看它拒绝猜测。** `ephe configure` 只写入一次选择；未做选择的机器会以失败关闭并给出解决方式，而不是回退到隐藏的默认值（[上面的第 2 步](#最初两分钟)）。
2. **观察一组智能体在并行工作树中协作。** `ephe agents` 打印每个运行实例及其状态与时长，随后 `ephe changes <workspace>` 按路径列出每个运行实例构建的内容，以及每个差异的摘要：

   ```text
   $ ephe agents
   1 live workspace (register ~/.ephe/workspaces/register.json)
   cb9f70d9  probe-n1  dirty  age 8s
   $ ephe changes cb9f70d9
   1 change set for /…/workspaces/cb9f70d9 (newest first)
   cs-20261014T141323Z-b519db23  draft  1 file  2026-10-14T14:13:23  probe: one file …
       create  docs/n1-probe.txt  sha256:8031de4f05e6
   ```

3. **在智能体与主干之间设置审查门槛。** `ephe review` 记录裁决；批准自己的工作会被拒绝，没有裁决的发布同样会被拒绝：

   ```text
   $ ephe review cs-20261014T141323Z-b519db23 approve --reviewer probe-n1 --reason "docs/n1-probe.txt:1:the author cannot approve its own set"
   Error: probe-n1 authored cs-20261014T141323Z-b519db23 and cannot approve it
     Fix: nothing was recorded: a verdict needs a reason inside the change set and a reviewer other than its author
   $ ephe publish cs-20261014T141344Z-f40dcdf2 --dry-run
   Error: cs-20261014T141344Z-f40dcdf2 may not publish: no verdict is recorded
     Fix: ephe review cs-20261014T141344Z-f40dcdf2 approve --reviewer <reviewer> --reason <path:line:why>
   ```

   由非作者审查者给出裁决后，同一命令会记录它并把集合移动到 `review`；`ephe publish --target <branch>` 随后要么落地集合中的全部文件，要么一个都不落地。
4. **限制会话存储的增长。** `ephe prune` 报告将释放多少空间且不做更改；加上 `--apply` 才会执行：

   ```text
   $ ephe prune
   Session store: ~/.ephe/sessions
   Holds 8942 files (3.9 MB): 2666 tasks a list shows, 6276 files no list reaches.
   Dry run: would delete 2079 files, freeing 2.1 MB. Nothing was changed — repeat with --apply.
   ```

5. **从手机使用。** 以 `ephe start --lan --open` 启动，在应用中打开 **Settings → Mobile** 并按面板上的三步操作：点击 **Connect mobile**，用同一网络中的手机扫描二维码，然后在移动版 PWA 中对话。公网访问是独立的显式选项；完整说明见 [docs/MOBILE.md](docs/MOBILE.md)。

## Ephe 是什么，不是什么

Ephe 是一个面向个人 SI 智能体的本地 Web 应用与 Python 后端——这里的 SI 指 *超级智能*。工作单元是“单元（cell）”：它在你的机器上运行，每次工具调用与审批决定都会写入记录，会话结束时该单元被销毁。除非你主动保留，否则不会留下任何东西：

| 能力 | 默认行为 | 网络行为 |
|---|---|---|
| 与所选模型对话 | 由你在应用内选择——没有静默默认 | 本地引擎在模型安装后无需互联网 |
| 图像理解 / OCR | 由你在应用内选择（本地 Ollama 可离线工作） | 模型安装后无需互联网 |
| 文件、PDF、个人资料、记忆 | 本地磁盘 | 无需互联网 |
| 二维码手机访问 | 局域网 | 公网手机隧道属于可选的在线功能 |
| Shell 与桌面操作 | 需要审批 | 仅本地，除非某个工具显式使用互联网 |
| `/research` | 未确认前禁用 | 可选的在线网页检索 |
| TTS 服务集成 | 可选 | 依赖互联网与提供商——安装后可本地使用 [Piper TTS](docs/VOICE.md)；云服务需要显式开启 |
| 自定义 Ollama 服务器 | 高级选项，需显式开启 | 本机或局域网端点 |
| 兼容 OpenAI 的 API | 高级选项，需显式开启 | 你配置的 API 提供商 |
| 沙盒代码执行（`run_sandboxed_code`） | 高级选项，需显式开启 | `pip install 'ephe[sandbox]'`——本地 WASI 沙盒（Ephemora Cell），无网络、无宿主机访问 |

这里的“本地优先”意味着：一旦你在应用内选好引擎（Ollama 或兼容 OpenAI 的端点），核心产品即可在本地工作，并且本地引擎与远程引擎地位相同。它不意味着每个可选集成都离线，也不意味着会静默预选某个引擎。

引擎选择是决定 Ephe 是什么、不是什么的分界线。选好引擎后的默认构建：

- **没有云服务，没有账号。** 本地路径在你的机器上运行，无需注册；没有遥测端点：唯一离开机器的调用是更新检查，它向 GitHub 询问最新版本。
- **不附带模型与模型包。** Ephe 不发布权重。安装器会检测正在运行的 Ollama 并到此为止；它从不安装 Ollama，也从不拉取模型标签。未选择引擎时，应用会等待并说明两种解决方式。
- **不是多用户服务器。** 一个实例在一台机器上服务一个人。
- **不是应用商店应用。** 手机界面就是通过你的网络访问的同一个 PWA；没有 iOS 或 Android 构建。
- **默认不爬取。** `/research`、远程引擎、公网手机访问与外部 TTS 都是显式路径；其余功能用离线引擎即可完成。
- **没有第二个原生应用。** Tauri 桌面外壳是 PWA 的轻量封装；`docs/` 中的 v2 实验不是发布界面。

## 桌面外壳

`ephe desktop` 构建 Tauri 外壳，安装到 `/Applications` 并打开。窗口承载同一个 PWA 和同一个 Python 后端；底层的原生层增加了以下平台能力：

```bash
ephe desktop               # 构建、安装到 /Applications 并打开
ephe desktop --dev         # 使用开发 URL 运行实时外壳
ephe desktop --no-install  # 保留构建副本而不安装
```

| 能力 | 实现 |
|---|---|
| 托盘图标（显示 / 隐藏 / 退出 / 新建会话）、原生通知，以及替代手输路径的原生文件对话框 | `app/src-tauri/src/lib.rs`（`tray-icon`）、`tauri-plugin-notification`、`tauri-plugin-dialog` |
| 后端监管：启动并停止 `~/.ephe/desktop.json` 中记录的 Python 后端；记录缺失时明确说明，而不是猜测解释器 | `app/src-tauri/src/backend.rs` |
| 引擎密钥存入操作系统钥匙串（macOS Keychain / Linux SecretService），并以 `0600` 密钥文件作为回退 | `core/engine_config.py` |
| 运行期间保持唤醒（macOS 上使用 `caffeinate`） | `app/src-tauri/src/lib.rs`（`set_keep_awake`） |
| 浏览器面板：子 WebView，因此发送 `X-Frame-Options` 的页面也能加载，而不会像 `<iframe>` 那样显示空白 | `app/src-tauri/src/browser.rs` |
| 单实例：配置目录中的套接字位于运行中的应用之前，并以 `tauri-plugin-single-instance` 作为跨平台兜底 | `app/src-tauri/src/instance.rs` |
| 与应用自身更新检查相连的签名自动更新器 | `tauri-plugin-updater`、`tauri-plugin-process` |

## 获取帮助

索引在 [`docs/`](docs/README.md)：[快速上手](docs/QUICKSTART.md)、[安装指南](docs/INSTALL.md)、[架构](docs/ARCHITECTURE.md)、[CLI 参考](docs/CLI.md)、基准方法论（[benchmark-mapping.md](docs/benchmark-mapping.md)）、插件格式规范（[PLUGINS.md](docs/PLUGINS.md)）、引擎切换指南（[SWITCHING.md](docs/SWITCHING.md)）以及演示媒体。

- Bug 与功能请求：GitHub [issue 跟踪器](https://github.com/bemlerlabs/ephe/issues)——仓库中包含 `bug_report` 与 `feature_request` 模板。
- 问题与发布说明：[Telegram 频道](docs/TELEGRAM.md)。
- 安全报告：使用 [SECURITY.md](SECURITY.md) 中的私有渠道，绝不要公开提交 issue。
- 贡献：[CONTRIBUTING.md](CONTRIBUTING.md)——fork、创建分支、添加或更新 Given-When-Then 测试、先运行最相关的检查，并使用模板提交 pull request。

## 适用对象

**在家自用。** Ephe 在你的机器上运行，状态也保存在你的机器上。没有账号、没有遥测、没有位于链路上的我们的服务器。安装、使用、保留。

**学习、测试、贡献。** 欢迎。测试就在本仓库中，架构已有文档，一个修复 bug 或润色一句话的 pull request 比一个 Star 更有价值。见 [CONTRIBUTING.md](CONTRIBUTING.md)。

**生产使用。** 需要商业许可证。含义就是：将 Ephe 用于真实工作，在工作场所或公司内部使用，或作为你提供的产品或服务的一部分。授权范围是 `None`，许可证中的其他条款均不覆盖这种使用。请联系我们；档位与流程见 [COMMERCIAL.md](COMMERCIAL.md)。

## 许可证

Business Source License 1.1（BUSL-1.1）——源码可见，非生产用途免费：阅读、运行、修改、构建、评估、贡献。**生产使用需要商业许可证**，即把 Ephe 用于真实工作、在工作场所或公司内部使用，或作为你提供的产品或服务的一部分。见 [COMMERCIAL.md](COMMERCIAL.md)。

每个版本在首次公开发布四周年后转为 Apache License 2.0，因此这里发布的一切都会在四年后成为普通开源软件。具体条款见 [LICENSE](LICENSE)；你通过贡献授予我们的权利见 [CONTRIBUTING.md](CONTRIBUTING.md)。
