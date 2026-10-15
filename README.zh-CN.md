# AI R&D Digest · AI 情报订阅

[English](README.md) | **简体中文**

让本机 Codex 根据**你关注的主题**，精选 Anthropic 和 OpenAI 的官方研究与重大产品更新，生成简短中文摘要，合并推送到飞书群。

你可以关注 AI 编程、Agent、模型与 API、科研加速，也可以加入医疗健康、生命科学、教育或其他主题。读者背景、关注主题、优先级和排除项都可以配置。

## 功能

- Codex 使用当前登录账户筛选文章、撰写摘要和复核事实，无需额外模型 API Key。
- 官方索引、RSS、Sitemap 发现新文章；必要时使用 Codex 网页工具补查原文。
- 每天最多一条飞书汇总，无合格新内容时静默。
- SQLite 永久记录已发送 URL、标题和研究标识，代码更新后仍保留历史。
- 进程锁、发送前持久化保留和成功回执防止重复发送；结果不明的发送等待人工核实。
- Windows 用户级 DPAPI 加密保存 Webhook。Python 3.11+，全部使用标准库。

## 简易使用：直接交给 Codex

1. 准备 Python 3.11+ 和已登录的 Codex 桌面应用。
2. 把飞书自定义机器人的 Webhook 保存为本机私密文件，例如项目目录中的 `boturl.txt`。该文件已被 Git 忽略；不要把真实地址贴到公开聊天或提交到仓库。
3. 在 Codex 中打开项目目录，发送下面的指令。尚未下载项目时，也可以让 Codex 根据指令克隆。

```text
请在本机部署 https://github.com/Yuiffy/ai-rd-digest。
先检查本地是否已有项目；没有则克隆，已有则复用，不覆盖个人配置或去重历史。
阅读 README.zh-CN.md、EDITORIAL.md 和 RUNBOOK.md，执行 show-config 检查有效配置。

我想关注：AI 编程、Agent 工具链、模型与 API 的重大更新。
读者背景：希望把 AI 用于实际工作的个人或团队。
请将这些偏好写入 config.local.json；首次安装的首期范围设为本月1日至今天。
Webhook 在本机 boturl.txt 中；若找不到，只向我询问文件路径，不展示其内容。

使用当前登录的 Codex 完成文章筛选、中文摘要与事实审核，不调用额外模型 API。
先检查网络和本机定时任务能力，完成不发送的真实干跑，再发送一次飞书测试并检查成功响应。
首次安装时处理首期精选；若已发送过首期或今天已发送日报，则跳过，不要重置历史或重复测试。
最后创建或更新唯一的本机每日任务，每天北京时间09:30执行，复用 EDITORIAL.md 的流程。
每期最多6篇，无值得推荐的新内容不发消息；保持去重记录、Webhook与本机配置私密。
请实际完成配置，核实日程已启用，汇报发送回执及运行条件；如某项能力不可用，明确指出阻碍。
```

这条指令是给 Codex 的安装任务，不会因克隆仓库或运行 Python 就自动创建日程。Codex 需要具备本地文件、网络和定时任务权限；缺少能力时仍需完成相应授权或配置。

## 随时改变关注主题

可以直接告诉 Codex：

```text
把 AI 情报订阅的关注主题改成“医疗健康 AI、生命科学、Agent 可靠性”，
读者背景改成“研究人员和产品开发者”。更新 config.local.json 并用 show-config 核验。
保留现有定时任务和全部去重历史，不发送测试或补发旧文章。
```

也可以手动新建 `config.local.json`：

```json
{
  "editorial": {
    "audience": "研究人员和产品开发者",
    "topics": ["医疗健康 AI", "生命科学", "Agent 可靠性"]
  },
  "max_articles": 4
}
```

`config.json` 提供共享默认值，`config.local.json` 保存个人覆盖项且不会提交 Git。字典递归合并，数组整体替换；未覆盖的字段沿用默认值。完整示例见 [config.local.example.json](config.local.example.json)。

| 想调整的内容 | 修改位置 |
| --- | --- |
| 读者与关注主题 | `editorial.audience`、`editorial.topics` |
| 选题优先级与排除项 | `editorial.priorities.P0/P1/P2`、`editorial.exclude` |
| 最多篇数、首次文章起始日 | `max_articles`、`start_date`；起始日不会重置已完成的首期 |
| 官方网站、RSS、Sitemap | `sources`，包括官方域名白名单与发现入口 |
| 每日时间与时区 | Codex 中的每日任务，修改 JSON 不会更改日程 |
| 代理 | 本机状态目录中的 `settings.json`，详见维护说明 |

```shell
python local_digest.py show-config
```

以上命令只显示有效内容配置，不发送消息，也不要求先初始化数据库。主题变化由 Codex 在下次编辑时应用，摘要默认仍为中文。

## 运行条件与维护

电脑必须开机、联网并保持唤醒，Codex 必须运行、登录且额度可用；需要代理时，代理也要可用。聊天页面无需保持打开。09:30 是开始处理时间，送达会稍晚；没有配置关机或睡眠时的唤醒、执行或保证补跑机制。

默认数据目录为 Windows 的 `%LOCALAPPDATA%\AiRdDigest`。不要删除或重置 `state.sqlite3`。没有额外模型 API 或云服务器费用，但使用现有 Codex 额度和本机资源。抓取覆盖不足会报告故障，不能当作“没有新内容”。

- [维护说明](RUNBOOK.md)：秘密配置、代理、持久化、手工运行与发送恢复。
- [编辑流程](EDITORIAL.md)：选题、原文证据、中文摘要与事实边界。
- [MIT License](LICENSE)。

本地验证：`python -m unittest discover -s tests -v`。测试不会发送消息。
