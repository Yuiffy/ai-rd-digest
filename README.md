# AI R&D Digest

**English** | [简体中文](README.zh-CN.md)

Let your local Codex select official Anthropic and OpenAI research and major product updates based on **the topics you care about**, write concise Chinese summaries, and deliver one digest to a Feishu group.

Follow AI coding, agents, models and APIs, or research acceleration. Add interests such as healthcare, life sciences, education, or other topics. Configure your audience, interests, priorities, and exclusions.

## Features

- Your signed-in Codex handles selection, summaries, and fact checking. No additional model API key.
- Discover articles through official indexes, RSS, and sitemaps; use Codex web tools to fill retrieval gaps.
- At most one Feishu digest per day. Stay silent when nothing qualifies.
- SQLite preserves sent URLs, titles, and story identifiers across code updates.
- Process locks, durable delivery reservations, and receipts guard against duplicates. Ambiguous deliveries require operator confirmation.
- Windows user-level DPAPI protects the webhook. Python 3.11+, standard library only.

## Quick start: ask Codex to set it up

1. Have Python 3.11+ and the Codex desktop app installed and signed in.
2. Save your Feishu custom bot webhook in a private local file, such as `boturl.txt` in the project directory. Git ignores that filename; keep the actual URL out of public chats and commits.
3. Open the project folder in Codex and send the prompt below. If you have not downloaded the project, Codex can clone it as part of setup.

```text
Set up https://github.com/Yuiffy/ai-rd-digest on this computer.
Check for an existing checkout first. Clone if absent; otherwise reuse it without overwriting personal settings or delivery history.
Read README.md, EDITORIAL.md, and RUNBOOK.md. Run show-config to inspect the effective configuration.

My interests: AI coding, agent tooling, and major model/API updates.
Audience: individuals or teams applying AI to practical work.
Save these preferences in config.local.json. On a fresh installation, set the first-edition window to the first day of this month through today.
My webhook is in the local boturl.txt file. If it is missing, ask only for its file path; never display its contents.

Use my signed-in Codex for selection, Chinese summaries, and fact checking. Do not call an additional model API.
Check connectivity and local scheduling support. Complete a real dry run without sending, then send one Feishu test and verify the success response.
Process the first edition on a fresh installation. If it or today's digest has already been sent, skip it; never reset history or repeat setup tests.
Finally, create or update a single local daily task for 09:30 Asia/Shanghai, following EDITORIAL.md on every run.
Include at most six articles; send nothing when no new article qualifies. Keep the webhook, history, and local settings private.
Actually complete setup, verify the enabled schedule, and report delivery receipts and operating requirements. State any unavailable capabilities or blockers clearly.
```

This prompt asks Codex to perform setup. Cloning the repository or running Python alone does not install a schedule. Codex needs local file access, network access, and scheduling support; unavailable capabilities may require authorization or configuration.

## Change your interests anytime

Ask Codex:

```text
Change my AI digest interests to healthcare AI, life sciences, and agent reliability.
Set the audience to researchers and product developers. Update config.local.json and verify with show-config.
Keep the existing schedule and all delivery history. Do not send a test or backfill old articles.
```

Or create `config.local.json` yourself:

```json
{
  "editorial": {
    "audience": "Researchers and product developers",
    "topics": ["Healthcare AI", "Life sciences", "Agent reliability"]
  },
  "max_articles": 4
}
```

`config.json` provides shared defaults. `config.local.json` contains personal overrides and is ignored by Git. Objects merge recursively; arrays replace the entire default array. Unspecified fields retain their defaults. See [config.local.example.json](config.local.example.json) for a fuller example.

| Setting | Where to change it |
| --- | --- |
| Audience and interests | `editorial.audience`, `editorial.topics` |
| Selection priorities and exclusions | `editorial.priorities.P0/P1/P2`, `editorial.exclude` |
| Maximum articles and first-edition date floor | `max_articles`, `start_date`; changing the date does not reset a completed first edition |
| Official sites, RSS, and sitemaps | `sources`, including allowed official hosts and discovery URLs |
| Daily time and timezone | The task in Codex; editing JSON does not change its schedule |
| Proxy | `settings.json` in the local state directory; see the runbook |

```shell
python local_digest.py show-config
```

This command prints the effective content configuration without sending or requiring an initialized database. Codex applies topic changes during its next editorial run. Summaries remain Chinese by default.

## Operating requirements and maintenance

Keep the computer powered on, awake, and online, with Codex running, signed in, and within its usage allowance. Keep your proxy available if needed. The chat page can be closed. The scheduled time starts processing; delivery takes additional time. There is no configured wake-from-sleep, power-on execution, or guaranteed catch-up mechanism.

On Windows, state defaults to `%LOCALAPPDATA%\AiRdDigest`. Preserve `state.sqlite3`; do not reset it during updates. There are no additional model API or cloud-server charges, but runs consume your existing Codex allowance and local resources. Incomplete source coverage is a failure, not an empty-news day.

- [Runbook](RUNBOOK.md) — secrets, proxies, storage, manual runs, and recovery (Chinese).
- [Editorial workflow](EDITORIAL.md) — selection, evidence, summaries, and factual boundaries (Chinese; Codex can follow these instructions).
- [MIT License](LICENSE).

Local checks: `python -m unittest discover -s tests -v`. Tests do not send messages.
