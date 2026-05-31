# pairing-admin

语言：[English](README.md) | **简体中文**

`pairing-admin` 给 Hermes 加了一层“聊天审批”的准入流程。

当 Hermes 没有对所有用户开放时，陌生用户通常会在真正进入 bot 前被拦住。装上这个插件后，陌生用户给 bot 发消息，插件会生成一个短申请码，管理员可以直接在聊天里批准或拒绝：

```text
/pa approve ABC123 Alice
```

适合你想继续开启 Hermes 白名单，又希望朋友、群成员或其他平台用户能自己发起准入申请，而不是每次都手动改 `.env` 的场景。

插件通过 `pre_gateway_dispatch` hook 运行，在 Hermes 常规授权流程之前处理符合条件的未授权用户，同时不依赖修改官方 Hermes 平台 adapter。

## 功能概览

- 把未授权用户的消息转换成待审批的准入申请。
- 直接由插件通知管理员，不消耗模型 token。
- 管理员可以在聊天中批准、拒绝、忽略、移除、拉黑和解除拉黑用户。
- 支持批量批准、批量拒绝、批量忽略、批量移除、批量设置备注。
- 按平台分组保存成员备注，让 `/pa users` 更好读。
- 支持可选的群聊申请入口，同时保持管理命令仅限私聊。
- 同一个待审批用户重复发消息时复用同一个 code，不重复刷管理员首条申请通知。
- 插件内置轻量待处理提醒，可配置提醒间隔。
- 待处理申请可以在超时后自动忽略。
- 实际访问授权仍写入 Hermes 内置 pairing store。

## 适用场景

当你的 Hermes bot 需要保持私有或半私有，但又不想每来一个新用户都手动改配置文件时，可以使用 `pairing-admin`。

适合：

- 个人 Hermes bot 分享给少量朋友使用。
- QQBot 或群相关 bot，希望新用户先申请，管理员同意后再使用。
- 一个 bot 接入多个消息平台，希望管理员能在任意已配置的管理员平台上审批所有受管平台的申请。
- Hermes 继续开启白名单，但新增用户通过聊天命令批准，而不是编辑 `.env` 和重启服务。
- 需要轻量成员管理：备注名、移除授权、拉黑、待处理提醒、过期申请清理。
- 对 token 消耗敏感，希望准入通知和提醒由插件自己处理，不进入模型对话。

它不适合当作完全开放的自助注册系统。除非管理员主动批准，否则申请人仍不能获得访问权。它也不是现实身份认证系统，只基于消息平台 adapter 提供的稳定 user ID 工作。

## 安全模型

管理员命令只建议在私聊中使用。管理员如果在群聊中发送 `/pa` 命令，插件只会回复一条简短提示并拒绝执行。这样可以避免申请码、用户 ID、黑名单和成员管理结果暴露在群聊里。

群聊申请入口默认关闭。开启后，插件只会在消息被视为“提到机器人”时创建申请。如果平台 adapter 本身已经只把群聊 at 机器人的事件转交给 Hermes，可以使用 `PAIRING_ADMIN_GROUP_TRIGGER=received`。

## 前置要求

- Hermes gateway 可用，并允许加载用户插件。
- 已接入 Hermes gateway 支持的消息平台。
- gateway 实例上存在 Hermes pairing store。
- 至少配置一个管理员 principal。

principal 格式：

```text
platform:user_id
```

示例：

```text
qqbot:USER_OPENID
telegram:TELEGRAM_USER_ID
```

## 安装

把插件目录放到 Hermes 用户插件目录：

```text
$HERMES_HOME/plugins/pairing-admin
```

目录中应包含：

```text
__init__.py
plugin.yaml
README.md
README.zh-CN.md
```

启用插件：

```bash
hermes plugins enable pairing-admin
```

安装或修改插件代码后，需要重启 Hermes gateway。

## 配置

配置可以写在 Hermes profile 的 `.env` 中，也可以来自进程环境变量。插件会先读进程环境变量，如果没有，再回退读取 `$HERMES_HOME/.env`。

最小配置：

```env
PAIRING_ADMIN_ADMINS=qqbot:YOUR_OPENID
PAIRING_ADMIN_PLATFORMS=qqbot
PAIRING_ADMIN_NOTIFY_ADMINS=true
PAIRING_ADMIN_NOTIFY_TARGETS=qqbot
```

配合 Hermes 用户白名单时建议保持：

```env
QQ_ALLOW_ALL_USERS=false
```

`QQ_ALLOWED_USERS` 仍然可以保留 bot owner 的 OpenID。通过 PA 批准的用户会写入 Hermes 内置 approved store。

授权按平台区分。例如批准 `qqbot:USER_ID` 不会自动批准这个人在 Telegram 上的身份。管理员权限与申请平台分离：只要某个账号被写入 `PAIRING_ADMIN_ADMINS`，它就可以在任意管理员平台上审批任意受管平台的申请。

完整配置示例：

```env
PAIRING_ADMIN_ADMINS=qqbot:YOUR_OPENID
PAIRING_ADMIN_PLATFORMS=qqbot
PAIRING_ADMIN_NOTIFY_ADMINS=true
PAIRING_ADMIN_NOTIFY_TARGETS=qqbot
PAIRING_ADMIN_ALLOW_GROUP_REQUESTS=false
PAIRING_ADMIN_GROUP_TRIGGER=mention
PAIRING_ADMIN_BOT_MENTIONS=@YourBotName
PAIRING_ADMIN_REMIND_ADMINS=true
PAIRING_ADMIN_REMIND_AFTER_SECONDS=600
PAIRING_ADMIN_REMIND_INTERVAL_SECONDS=1800
PAIRING_ADMIN_REMIND_CHECK_SECONDS=60
PAIRING_ADMIN_AUTO_IGNORE_AFTER_SECONDS=86400
```

## 配置项说明

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `PAIRING_ADMIN_ADMINS` | 空 | 管理员 principal，逗号分隔。格式为 `platform:user_id`。`*` 表示任何人都是管理员，不建议使用。 |
| `PAIRING_ADMIN_QQ_ADMINS` | 空 | 旧版 QQ 专用管理员列表。不带平台前缀时按 `qqbot:<id>` 处理。 |
| `PAIRING_ADMIN_PLATFORMS` | `qqbot` | 插件管理的平台，逗号分隔。`*` 表示管理全部平台。 |
| `PAIRING_ADMIN_NOTIFY_ADMINS` | `true` | 新申请创建时是否通知管理员。 |
| `PAIRING_ADMIN_NOTIFY_TARGETS` | 空 | 管理员通知目标过滤器。可以写平台名，如 `qqbot`，也可以写精确 principal，如 `qqbot:USER_ID`。空值表示通知所有管理员。 |
| `PAIRING_ADMIN_ALLOW_GROUP_REQUESTS` | `false` | 是否允许群聊中触发准入申请。 |
| `PAIRING_ADMIN_GROUP_TRIGGER` | `mention` | 群聊触发模式。支持 `mention`、`received`、`always`。 |
| `PAIRING_ADMIN_BOT_MENTIONS` | 空 | `mention` 模式下用于文本匹配的机器人提及标记，逗号分隔，例如 `@Hermes`。 |
| `PAIRING_ADMIN_BOT_ID` | 空 | 可选机器人 ID，用于 mention metadata 匹配。 |
| `PAIRING_ADMIN_REMIND_ADMINS` | `true` | 是否启用待处理申请提醒。 |
| `PAIRING_ADMIN_REMIND_AFTER_SECONDS` | `600` | 申请等待多久后开始提醒管理员。 |
| `PAIRING_ADMIN_REMIND_INTERVAL_SECONDS` | `1800` | 两次待处理提醒之间的最小间隔。 |
| `PAIRING_ADMIN_REMIND_CHECK_SECONDS` | `60` | 后台提醒循环的检查间隔。 |
| `PAIRING_ADMIN_AUTO_IGNORE_AFTER_SECONDS` | `86400` | 待处理申请超过多少秒后自动忽略。设为 `0` 表示关闭。 |

## 通知目标

`PAIRING_ADMIN_ADMINS` 决定谁可以执行管理员命令。`PAIRING_ADMIN_NOTIFY_TARGETS` 只决定新申请通知和待处理提醒发到哪里。

`PAIRING_ADMIN_NOTIFY_TARGETS` 为空时，所有已配置管理员都会收到申请通知。设置后，每一项可以是平台名，也可以是精确的管理员 principal：

```env
PAIRING_ADMIN_NOTIFY_TARGETS=qqbot
PAIRING_ADMIN_NOTIFY_TARGETS=qqbot:YOUR_OPENID,telegram:ADMIN_USER_ID
```

如果同一个管理员绑定了多个平台，但只想在其中一两个平台收到 PA 提醒，可以用这个配置过滤通知位置。

## 群聊触发模式

`PAIRING_ADMIN_GROUP_TRIGGER=mention` 会检查 mention metadata 和配置的文本标记。适合平台 adapter 会转发普通群聊消息，需要插件自行判断是否提到机器人的情况。

`PAIRING_ADMIN_GROUP_TRIGGER=received` 会把每一条收到的群聊事件都视为发给机器人的消息。只有当平台 adapter 已经把群聊消息过滤为 bot-at 事件时才建议使用。

`PAIRING_ADMIN_GROUP_TRIGGER=always` 与 `received` 等价，保留这个写法是为了让“所有群事件都触发”的意图更明确。

## 申请生命周期

1. 未授权用户私聊机器人，或者在开启群聊申请后发送面向机器人的群聊消息。
2. 插件检查该用户是否已被拉黑。
3. 如果该用户没有待处理申请，插件生成一个新的申请 code。
4. 插件通知配置的管理员目标。
5. 如果同一用户在申请未处理前继续发消息，插件复用已有 code，只更新 `last_seen_at`，不会重复发送首条申请通知。
6. 管理员批准、忽略、拒绝、拉黑，或者让申请超时自动忽略。
7. 批准时，插件写入 Hermes 内置 pairing store。

申请人每次被插件处理时都会收到一条“请等待管理员审批”的简短回复。同一个待审批用户重复发消息不会重复创建管理员首条申请通知，只会更新已有申请的 `last_seen_at` 时间。

## 管理员命令

管理员应在私聊中发送命令。

| 命令 | 说明 |
| --- | --- |
| `/pa help` | 显示帮助。 |
| `/pa pending` | 查看待处理申请。 |
| `/pa config` | 查看当前插件配置。 |
| `/pa auto-ignore 24h` | 覆盖自动忽略时间。支持 `s`、`m`、`h`、`d`。 |
| `/pa auto-ignore off` | 关闭自动忽略。 |
| `/pa users [platform]` | 按平台查看已批准用户。 |
| `/pa approve CODE [alias]` | 批准一个申请，可顺手设置备注。 |
| `/pa approve CODE1 CODE2` | 批量批准多个申请。 |
| `/pa approve CODE=alias CODE2=alias2` | 批量批准并设置备注。 |
| `/pa approve all` | 批准所有待处理申请。 |
| `/pa ignore CODE...` | 静默忽略待处理申请，不通知申请人。 |
| `/pa deny CODE...` | 拒绝待处理申请，并通知申请人。 |
| `/pa alias platform:user_id=alias ...` | 设置或更新成员备注。 |
| `/pa revoke platform:user_id ...` | 移除已批准访问权。 |
| `/pa delete platform:user_id ...` | 与 revoke 相同。 |
| `/pa block platform:user_id [reason]` | 移除访问权、清理待处理申请并拉黑用户。 |
| `/pa unblock platform:user_id` | 从黑名单移除用户。 |
| `/pa blocked` | 查看黑名单。 |

命令别名包括：`p` 表示 `pending`，`u` 表示 `users`，`autoignore` 或 `ttl` 表示 `auto-ignore`，`remove`、`rm`、`delete`、`del` 表示 `revoke`，`ban` 表示 `block`，`unban` 表示 `unblock`，`blacklist` 表示 `blocked`，`rename` 或 `note` 表示 `alias`。

## 使用示例

批准一个申请：

```text
/pa approve ABC123
```

批准并设置备注：

```text
/pa approve ABC123 Alice
```

批量批准：

```text
/pa approve ABC123 DEF456
```

批量批准并设置备注：

```text
/pa approve ABC123=Alice DEF456=Bob
```

设置成员备注：

```text
/pa alias qqbot:USER_A=Alice qqbot:USER_B=Bob
```

批量移除访问权：

```text
/pa revoke qqbot:USER_A qqbot:USER_B
```

忽略所有当前待处理申请：

```text
/pa ignore all
```

修改自动忽略时间：

```text
/pa auto-ignore 7d
```

## 状态文件

插件状态存储在：

```text
$HERMES_HOME/pairing-admin/state.json
```

重要字段：

| 字段 | 用途 |
| --- | --- |
| `requests` | 待处理申请，按申请 code 存储。 |
| `members` | 按平台分组的成员元数据。 |
| `aliases` | 兼容用备注映射，key 为 `platform:user_id`。 |
| `blocked` | 黑名单用户，key 为 `platform:user_id`。 |
| `ignored` | 已忽略申请记录，key 为 `platform:user_id`。 |
| `audit` | 最近的申请和管理员操作历史。 |

插件通过 Hermes pairing store 写入正式授权。插件本地的 `members` 和
`aliases` 用于展示和备注，不是访问授权的最终来源。

运行环境允许时，状态文件会以较严格的文件权限写入。请把它当作私有数据处理：它可能包含用户 ID、申请消息、成员备注、黑名单和最近的审计记录。

## 排障

如果同一个待审批用户多次发消息导致管理员被重复提醒，请确认部署版本包含 pending request 通知去重。预期行为是同一个 pending code 只发送一次首条管理员通知。

如果群聊申请没有触发，请检查：

- `PAIRING_ADMIN_ALLOW_GROUP_REQUESTS=true`
- `PAIRING_ADMIN_GROUP_TRIGGER` 是否匹配平台 adapter 行为。
- 平台 adapter 是否真的把群聊 bot-at 事件转发给 Hermes。
- 平台是否包含在 `PAIRING_ADMIN_PLATFORMS` 中。

如果群聊申请能创建，但机器人无法在群里回复，问题可能在平台 adapter 或平台侧发送权限。创建 PA 申请和群消息发送是两个不同步骤。

如果配置看起来没有生效，请检查配置是在进程环境变量里，还是在 `$HERMES_HOME/.env` 里。插件支持两者，但有效的 Hermes home 必须正确。

如果申请里显示 `user: (unknown)`，说明平台事件没有提供显示名。这不影响审批，可以用 `/pa approve CODE alias` 或 `/pa alias platform:user_id=alias` 补一个好读的备注。

如果管理员收不到通知，需要同时检查两个配置：管理员必须在 `PAIRING_ADMIN_ADMINS` 中，并且 `PAIRING_ADMIN_NOTIFY_TARGETS` 要么为空，要么匹配这个管理员的平台或精确的 `platform:user_id` principal。

## 平台说明

插件运行在 gateway 层，并不是写死只支持 QQBot，但当前实现只在 Hermes QQBot adapter 上完成过实测。其他平台属于设计上兼容，但在对应平台跑完下面的 smoke test 之前，都应视为未验证。

其他平台 adapter 如果要正常工作，至少应提供这些事件字段：

- `event.text`：消息文本，用于命令、申请消息和 mention 文本匹配。
- `event.source.platform`：平台名。这个值必须和 `PAIRING_ADMIN_PLATFORMS`、`PAIRING_ADMIN_ADMINS`、`PAIRING_ADMIN_NOTIFY_TARGETS` 中使用的平台名一致。
- `event.source.user_id`：该平台上的稳定用户身份。
- `event.source.chat_id`：回复和申请确认消息使用的发送目标。
- `event.source.chat_type`：私聊应是 `c2c`、`dm`、`private` 之一；群聊应是 `group`、`guild`、`channel`、`group_at_message`、`group_message` 之一。
- `event.source.user_name`：可选显示名。没有这个字段时，申请里会显示 `user: (unknown)`，管理员可以审批时顺手加 alias。

adapter 还必须通过 Hermes 的 `gateway.adapters` 暴露 `send(chat_id, content)`。管理员通知、申请人确认、批准通知、拒绝通知和命令回复都走这条发送路径。

非 QQBot adapter 的最小配置示例：

```env
PAIRING_ADMIN_ADMINS=telegram:ADMIN_USER_ID
PAIRING_ADMIN_PLATFORMS=telegram
PAIRING_ADMIN_NOTIFY_TARGETS=telegram
```

多平台示例：

```env
PAIRING_ADMIN_ADMINS=qqbot:QQ_ADMIN_OPENID,telegram:TG_ADMIN_USER_ID
PAIRING_ADMIN_PLATFORMS=qqbot,telegram
PAIRING_ADMIN_NOTIFY_TARGETS=telegram
```

在这个多平台示例里，两个管理员都可以审批受管平台的申请，但 PA 通知只会发到 Telegram。

群聊申请支持取决于 adapter 行为：

- adapter 会转发普通群聊消息，需要插件判断是否提到机器人时，使用 `PAIRING_ADMIN_GROUP_TRIGGER=mention`。同时配置 `PAIRING_ADMIN_BOT_MENTIONS`，如果平台能提供机器人 ID，也配置 `PAIRING_ADMIN_BOT_ID`。
- adapter 已经在进入 Hermes 前过滤好了群事件，只把面向机器人的消息交给 Hermes 时，使用 `PAIRING_ADMIN_GROUP_TRIGGER=received`。
- 只有当 Hermes 收到的每一条群事件都应该视为 PA 申请尝试时，才使用 `PAIRING_ADMIN_GROUP_TRIGGER=always`。

把某个新平台标为“已支持”之前，至少验证：

1. 未授权用户私聊会创建一个 pending request，并通知管理员。
2. 同一个待审批用户重复发消息会复用同一个 code。
3. 管理员私聊发送 `/pa approve CODE` 后，该用户获得访问权。
4. `/pa users platform` 能列出已批准用户。
5. 如果开启群聊申请，面向机器人的群聊消息能创建 request。
6. 如果平台允许群聊回复，申请人能收到轻量确认消息；如果平台不允许，申请创建仍可能成功，但群发送会在 adapter 或平台权限层失败。

## 贡献

欢迎 fork 和提交 PR，尤其欢迎测试 QQBot 之外的 Hermes 平台 adapter。

如果你测试了新的平台 adapter，可以开 PR 补充：

- adapter/平台名称，以及测试时使用的 Hermes 版本。
- 该 adapter 暴露的事件字段，尤其是 `source.platform`、`source.user_id`、`source.chat_id`、`source.chat_type`。
- 私聊申请、管理员命令、批准、移除、提醒是否正常。
- 群聊申请是否正常，以及需要使用哪个 `PAIRING_ADMIN_GROUP_TRIGGER` 模式。
- 平台侧或 adapter 侧的权限限制，例如能创建群申请，但不能发送群回复。

只改文档、确认某个平台状态的 PR 也很有价值。代码改动尽量不要修改 Hermes 官方 adapter，除非 adapter 本身确实有 bug；平台差异通常应写进文档，或者在这个插件内部兼容。

## 开发检查

常用本地检查：

```bash
python3 -m py_compile __init__.py
git diff --check
```

建议 smoke test：

- 重复待处理申请：同一个未授权 principal 连续触发两次，确认只发送一条管理员通知。
- 群聊触发：开启群聊申请后，确认群聊事件能创建 request。
- 管理员群聊命令：确认群里 `/pa help` 被拒绝，不会执行。
- 批量命令：确认批量 approve、alias、revoke、ignore、deny 路径正常。
