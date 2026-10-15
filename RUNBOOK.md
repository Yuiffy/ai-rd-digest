# 维护说明

Python 3.11+，全部使用标准库。无需安装模型 SDK 或购买 API 额度。

本机 Codex 每天北京时间 09:30 唤醒已授权的聊天，读取 `EDITORIAL.md` 执行。09:30 是开始处理时间，抓取与摘要需要时间，送达不保证精确到分钟。电脑要开机、联网、保持唤醒，Codex 应用要运行并登录，账户需有可用额度，项目和数据目录要可访问。对话页可关闭。手动关机/睡眠或退出 Codex 时不能执行；没有配置系统唤醒/开机任务，不保证错过的日程补跑。

## 安装与秘密

```
python local_digest.py initialize
python local_digest.py install-secret --file <本机私密Webhook文件>
```

Windows 的 Webhook 使用当前用户 DPAPI 加密，保存在状态目录的 webhook.dpapi。仅当前 Windows 用户可解密；换用户/重装系统需重新安装秘密。跨平台可设置 FEISHU_WEBHOOK 环境变量。切勿打印秘密、提交 boturl.txt 或日志中的网络请求对象。本项目不读取任何模型 API Key。原始 Webhook 文件不属于仓库，仍需妥善保管。

## 固定持久化位置

默认 `%LOCALAPPDATA%\AiRdDigest`（Windows），可通过 AI_DIGEST_HOME 指定固定绝对目录。不要在日常任务中临时改变此值或指向 worktree。state.sqlite3 保存永久已推送 URL/标题/story_key、首期截止日期、每日投递和独立成功回执；process.lock 是进程锁；backups/ 是 SQLite 一致性备份。代码重装/重新克隆不会删除它。删除数据库会损失去重历史，禁止“遇到错误就重新初始化”。initialize 使用 INSERT OR IGNORE，已有历史不会重置。若数据库丢失，普通运行会报错而非创建空历史。

settings.json 可写 `{"https_proxy":"http://127.0.0.1:7890"}`，供官网抓取使用。Clash Verge 需保持运行且端口可用；不要把带密码的代理地址提交到仓库。飞书 webhook 默认使用单独的直连路由（TUN 可继续接管），如确有必要可在本机 settings.json 设置 feishu_proxy。

## 手工运行与核验

```
python local_digest.py status
python local_digest.py collect --out work/sources-http.json
```

按 EDITORIAL.md 用已登录 Codex 阅读与审核，生成 sources.json、review.json，然后：

```
python local_digest.py prepare --sources work/sources.json --review work/review.json --out work/prepared.json
python local_digest.py send --file work/prepared.json
python local_digest.py status
python local_digest.py backup
```

prepare 不发送、不改去重历史；send 会重新校验稿件和历史，当天已推送则静默。只在安装连通性测试时使用 `python local_digest.py test-send`。首期标题按执行月份自动生成为「AI 研发情报｜N 月首期精选」，成功后永久记住 first_complete 与 first_cutoff；之后只发截止日之后的新内容。

若发送结果不明，先人工查看群历史，确认后再选择一个：

```
python local_digest.py reconcile-sent --reason "用户核实群内已经收到"
python local_digest.py reconcile-not-sent --reason "用户核实群内未收到，允许重试"
```

不要猜测发送结果。状态已 accepted 的当天不支持强制补发第二条日报。

## 修改与测试

- 执行 `python local_digest.py show-config` 查看实际生效的配置，不需要先初始化数据库。
- 关注主题、读者背景、P0/P1/P2 和排除项：config.json 的 editorial；本机修改推荐写入 config.local.json。可复制 config.local.example.json 后编辑；该本机文件不会提交 Git。字典递归合并，数组整体替换。
- 网站域名、RSS、索引、Sitemap、首期起始日、最大篇数：config.json；也支持 config.local.json 覆盖。新增来源需同时配置官方 hosts 和发现入口。
- 中文摘要风格、事实边界和每日编辑流程：EDITORIAL.md。
- 卡片布局和网页抽取：digest.py。
- 代理、持久化、发送保护：local_digest.py / 本机 settings.json。
- 每天时间、聊天提示：Codex 内的每日任务；修改文件不会自动改变日程。
- 验证：`python -m unittest discover -s tests -v`。测试不访问网络、不发送消息。

代码、云主机和额外模型 API 费用为 0；占用现有 Codex 订阅额度、本机电费与网络/代理成本。额度用完、需要登录或无人值守权限不足都会影响运行；在 Codex 日程中检查失败记录。
