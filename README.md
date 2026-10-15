# AI R&D Digest / AI 研发情报

用已登录的本机 Codex 每天精选 Anthropic / OpenAI 官方研究与重大产品更新，生成中文飞书卡片。面向软件研发、Agent 工程和医疗健康团队。

- 无额外模型 API、云服务器、GitHub Actions 或 Vercel。
- 官方索引、RSS、Sitemap 发现；Codex 网页工具备用读取。
- 中文选题与摘要由 Codex 完成，脚本校验日期、正文证据和长度。
- SQLite 永久去重，Windows 用户级 DPAPI 保存 Webhook。
- 每日一条汇总，无内容静默；锁与持久化投递保留避免重发。
- 先干跑、审核，再真实发送。首次只从配置起始日至当天精选，随后仅推送新稿。

这不是独立的 Python 模型代理：必须由已登录且运行中的 Codex 执行编辑流程。电脑休眠、关机或 Codex 退出时不能工作，无法保证秒级定时。Web 抓取可能受反爬与网络影响，覆盖不足会报告故障。

从 [维护说明](RUNBOOK.md) 开始，编辑规则见 [EDITORIAL.md](EDITORIAL.md)。Python 3.11+ 标准库，MIT License。
