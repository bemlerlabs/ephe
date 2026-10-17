<p align="center">
  <a href="README.zh-CN.md">中文</a> | <a href="README.es.md">Español</a> | <a href="README.md">English</a>
</p>

# Ephe — 私有、本地的瞬时 SI 代理

**本地优先的 PWA + FastAPI，运行在你自己的机器上。无账号、无遥测；在线功能（联网检索、远程引擎）均为显式选择。引擎由你决定——本地 Ollama、远程 Ollama，或任何兼容 OpenAI 的端点（DGX Spark、vLLM、SGLang）。没有静默默认：在你选择之前，应用会明确告知。**

<table>
<tr><td><b>闭环学习</b></td><td>51 个内置技能包（含 rubric+golden 验证）、确定性技能快速路径、个人记忆库与全文会话检索——你的历史持续积累，而不是蒸发。</td></tr>
<tr><td><b>审批把关的工具</b></td><td>文件系统、Shell、浏览器与文档工具均受安全配置约束（strict / session / autonomous）。写入需要同意；Ask 模式完全不使用工具。</td></tr>
<tr><td><b>可测量，而非空谈</b></td><td>可复现的代理基准（60 任务矩阵 + TAU/GAIA 启发的 pass³ 映射）每轮对真实流式端点运行——发布所用的门槛，也是验证所用的门槛。</td></tr>
</table>

## 快速安装

```bash
curl -fsSL https://raw.githubusercontent.com/bemlerlabs/ephe/main/install.sh | bash
```

安装器将应用放到 `~/Documents/Ephe`，构建 PWA，并启动本地服务器（默认 `http://127.0.0.1:8765`）。它不会安装 Ollama，也不会下载任何模型——首次运行时你在应用内选择引擎。

## 文档

完整功能、架构、测试与安全说明见 [英文 README](README.md)（主文档）。

## 许可

[BUSL-1.1](LICENSE)
