# pairing-admin

Language: **English** | [简体中文](README.zh-CN.md)

`pairing-admin` is a Hermes gateway plugin for admin-mediated user admission.
It lets unapproved messaging users request access, then lets configured admins
approve, ignore, deny, revoke, block, and manage those users directly from chat.

The plugin is designed to be independent from official Hermes platform plugins.
It registers the `pre_gateway_dispatch` hook and handles eligible unapproved
users before Hermes' normal authorization flow.

## What It Does

- Creates pairing requests for unapproved users.
- Sends request details to configured admins without consuming model tokens.
- Lets admins approve or deny requests from chat.
- Supports batch approve, batch deny, batch ignore, batch revoke, and batch alias
  operations.
- Stores member remarks grouped by platform.
- Supports optional group-chat request intake while keeping admin actions DM-only.
- Deduplicates repeat messages from the same pending user, so admins only get
  one first-create notification per pending code.
- Sends lightweight pending-request reminders on a configurable interval.
- Automatically ignores stale pending requests after a configurable timeout.
- Keeps access authorization in Hermes' built-in pairing store.

## Safety Model

Admin commands are intended for DMs. If an admin sends `/pa` in a group chat, the
plugin rejects the command with a short notice and does not execute it. This
prevents request codes, user IDs, blacklist entries, and member management
results from being exposed publicly.

Group request intake is optional and disabled by default. When enabled, group
messages are accepted only when the platform event is treated as a bot mention.
For adapters that already filter group messages to bot-at events, use
`PAIRING_ADMIN_GROUP_TRIGGER=received`.

## Requirements

- Hermes gateway with user plugins enabled.
- A messaging platform supported by Hermes' gateway.
- Hermes pairing store available on the gateway instance.
- At least one admin principal configured with `PAIRING_ADMIN_ADMINS`.

Principals use this format:

```text
platform:user_id
```

Examples:

```text
qqbot:USER_OPENID
telegram:TELEGRAM_USER_ID
```

## Installation

Place the plugin directory under the Hermes user plugins directory:

```text
$HERMES_HOME/plugins/pairing-admin
```

The directory should contain:

```text
__init__.py
plugin.yaml
README.md
README.zh-CN.md
```

Enable the plugin:

```bash
hermes plugins enable pairing-admin
```

Restart the Hermes gateway after installing or changing plugin code.

## Configuration

Set configuration in the Hermes profile `.env` or process environment. The
plugin reads process environment variables first, then falls back to
`$HERMES_HOME/.env`.

Minimal configuration:

```env
PAIRING_ADMIN_ADMINS=qqbot:YOUR_OPENID
PAIRING_ADMIN_PLATFORMS=qqbot
PAIRING_ADMIN_NOTIFY_ADMINS=true
PAIRING_ADMIN_NOTIFY_TARGETS=qqbot
```

Recommended with Hermes user allowlisting:

```env
QQ_ALLOW_ALL_USERS=false
```

`QQ_ALLOWED_USERS` can still contain the owner's OpenID. Approved users are
stored in Hermes' built-in pairing approved store.

Approval is platform-specific. For example, approving `qqbot:USER_ID` does not
automatically approve the same person on Telegram. Admin authority is separate:
an admin listed in `PAIRING_ADMIN_ADMINS` can approve requests from any managed
platform, even if the admin is operating from a different platform.

Full configuration example:

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

## Configuration Reference

| Variable | Default | Description |
| --- | --- | --- |
| `PAIRING_ADMIN_ADMINS` | empty | Comma-separated admin principals. Use `platform:user_id`. `*` allows any user to act as admin and is not recommended. |
| `PAIRING_ADMIN_QQ_ADMINS` | empty | Legacy QQ-only admin list. Values without a platform are treated as `qqbot:<id>`. |
| `PAIRING_ADMIN_PLATFORMS` | `qqbot` | Comma-separated managed platforms. Use `*` to manage all platforms. |
| `PAIRING_ADMIN_NOTIFY_ADMINS` | `true` | Whether to notify admins when a new request is created. |
| `PAIRING_ADMIN_NOTIFY_TARGETS` | empty | Optional notification filter. Accepts platform names such as `qqbot` or exact principals such as `qqbot:USER_ID`. Empty means all configured admins. |
| `PAIRING_ADMIN_ALLOW_GROUP_REQUESTS` | `false` | Enables pairing requests from group chats when the message is considered a bot mention. |
| `PAIRING_ADMIN_GROUP_TRIGGER` | `mention` | Group trigger mode. Supports `mention`, `received`, and `always`. |
| `PAIRING_ADMIN_BOT_MENTIONS` | empty | Comma-separated text markers used by `mention` mode, such as `@Hermes`. |
| `PAIRING_ADMIN_BOT_ID` | empty | Optional bot ID used by mention metadata matching. |
| `PAIRING_ADMIN_REMIND_ADMINS` | `true` | Enables lightweight pending-request reminders. |
| `PAIRING_ADMIN_REMIND_AFTER_SECONDS` | `600` | How old a request must be before reminders start. |
| `PAIRING_ADMIN_REMIND_INTERVAL_SECONDS` | `1800` | Minimum interval between pending-request reminders. |
| `PAIRING_ADMIN_REMIND_CHECK_SECONDS` | `60` | Background reminder loop check interval. |
| `PAIRING_ADMIN_AUTO_IGNORE_AFTER_SECONDS` | `86400` | Automatically ignore pending requests older than this many seconds. Set `0` to disable. |

## Notification Targeting

`PAIRING_ADMIN_ADMINS` defines who is allowed to run admin commands.
`PAIRING_ADMIN_NOTIFY_TARGETS` only controls where new request notifications and
pending reminders are sent.

When `PAIRING_ADMIN_NOTIFY_TARGETS` is empty, every configured admin receives
request notifications. When it is set, each value can be either a platform name
or an exact admin principal:

```env
PAIRING_ADMIN_NOTIFY_TARGETS=qqbot
PAIRING_ADMIN_NOTIFY_TARGETS=qqbot:YOUR_OPENID,telegram:ADMIN_USER_ID
```

This is useful when the same admin account is configured on multiple platforms
but should only receive PA prompts in one or two places.

## Group Request Modes

`PAIRING_ADMIN_GROUP_TRIGGER=mention` checks mention metadata and configured text
markers. Use this when the adapter forwards normal group messages and the plugin
needs to decide whether the bot was mentioned.

`PAIRING_ADMIN_GROUP_TRIGGER=received` treats every received group event as a
bot-directed message. Use this only when the platform adapter already filters
group events to bot-at messages.

`PAIRING_ADMIN_GROUP_TRIGGER=always` is equivalent to `received`; it is kept as
an explicit opt-in spelling for platforms where every group event should create
or update a request.

## Request Lifecycle

1. An unapproved user sends a DM or, if enabled, a bot-directed group message.
2. The plugin checks whether the user is blocked.
3. If no pending request exists, the plugin creates a new request code.
4. The plugin notifies configured admin targets.
5. If the same user sends more messages while the request is still pending, the
   plugin reuses the same code and updates `last_seen_at` without sending another
   first-create notification.
6. An admin approves, ignores, denies, blocks, or lets the request auto-expire.
7. Approval writes to Hermes' built-in pairing store.

Applicants get a short "please wait for approval" response whenever their
pending request is handled by the plugin. Duplicate applicant messages do not
create duplicate admin first-create notifications; they only update the existing
request's `last_seen_at` timestamp.

## Admin Commands

Admins should send commands in DM.

| Command | Description |
| --- | --- |
| `/pa help` | Show command help. |
| `/pa pending` | List pending requests. |
| `/pa config` | Show current plugin settings. |
| `/pa auto-ignore 24h` | Override automatic ignore timeout. Supports `s`, `m`, `h`, and `d`. |
| `/pa auto-ignore off` | Disable automatic ignore. |
| `/pa users [platform]` | List approved users grouped by platform. |
| `/pa approve CODE [alias]` | Approve one request and optionally set a remark. |
| `/pa approve CODE1 CODE2` | Approve multiple requests. |
| `/pa approve CODE=alias CODE2=alias2` | Batch approve and set remarks. |
| `/pa approve all` | Approve all pending requests. |
| `/pa ignore CODE...` | Silently remove pending requests. Applicants are not notified. |
| `/pa deny CODE...` | Deny pending requests and notify applicants. |
| `/pa alias platform:user_id=alias ...` | Set or update member remarks. |
| `/pa revoke platform:user_id ...` | Remove approved access. |
| `/pa delete platform:user_id ...` | Same as revoke. |
| `/pa block platform:user_id [reason]` | Revoke access, remove pending requests, and blacklist the user. |
| `/pa unblock platform:user_id` | Remove a user from the blacklist. |
| `/pa blocked` | List blacklisted users. |

Supported command aliases include `p` for `pending`, `u` for `users`,
`autoignore` or `ttl` for `auto-ignore`, `remove`, `rm`, `delete`, or `del` for
`revoke`, `ban` for `block`, `unban` for `unblock`, `blacklist` for `blocked`,
and `rename` or `note` for `alias`.

Short aliases:

```text
同意 CODE
批准 CODE
通过 CODE
拒绝 CODE
驳回 CODE
忽略 CODE
无视 CODE
```

## Examples

Approve one request:

```text
/pa approve ABC123
```

Approve and set a remark:

```text
/pa approve ABC123 Alice
```

Approve multiple requests:

```text
/pa approve ABC123 DEF456
```

Approve multiple requests with remarks:

```text
/pa approve ABC123=Alice DEF456=Bob
```

Set member remarks:

```text
/pa alias qqbot:USER_A=Alice qqbot:USER_B=Bob
```

Remove access for multiple users:

```text
/pa revoke qqbot:USER_A qqbot:USER_B
```

Ignore every current pending request:

```text
/pa ignore all
```

Change auto-ignore timeout:

```text
/pa auto-ignore 7d
```

## State

Plugin state is stored under:

```text
$HERMES_HOME/pairing-admin/state.json
```

Important state fields:

| Field | Purpose |
| --- | --- |
| `requests` | Pending pairing requests keyed by request code. |
| `members` | Member metadata grouped by platform. |
| `aliases` | Compatibility alias map keyed by `platform:user_id`. |
| `blocked` | Blacklisted users keyed by `platform:user_id`. |
| `ignored` | Ignored request records keyed by `platform:user_id`. |
| `audit` | Recent request/admin action history. |

The plugin writes approved access through Hermes' pairing store. Local member
metadata is used for display and remarks, not as the authorization source of
truth.

The state file is written with restrictive file permissions when the runtime
allows it. Treat it as private data: it can contain user IDs, request messages,
member remarks, blocked users, and recent audit entries.

## Troubleshooting

If repeated messages from the same pending user keep notifying admins, confirm
the deployed plugin version includes pending-request notification deduplication.
The expected behavior is one first-create admin notification per pending code.

If group requests do not trigger, check:

- `PAIRING_ADMIN_ALLOW_GROUP_REQUESTS=true`
- `PAIRING_ADMIN_GROUP_TRIGGER` matches the adapter behavior.
- The platform adapter actually forwards group bot-at events to Hermes.
- The platform is included in `PAIRING_ADMIN_PLATFORMS`.

If group request creation works but group replies fail, the issue may be in the
platform adapter or platform-side send permissions. Pairing request creation and
platform group message delivery are separate steps.

If configuration appears ignored, check whether the values are in the process
environment or in `$HERMES_HOME/.env`. The plugin supports both, but the
effective Hermes home must be correct.

If a request shows `user: (unknown)`, the platform event did not provide a
display name. The request can still be approved; use `/pa approve CODE alias` or
`/pa alias platform:user_id=alias` to add a readable remark.

If an admin does not receive notifications, verify both settings: the admin must
be listed in `PAIRING_ADMIN_ADMINS`, and `PAIRING_ADMIN_NOTIFY_TARGETS` must be
empty or match either that admin's platform or exact `platform:user_id`
principal.

## Platform Notes

The plugin is gateway-level and is not hard-coded to QQBot. It should work with
any Hermes platform adapter that exposes `source.platform`, `source.user_id`,
`source.chat_id`, `source.chat_type`, and supports adapter `send()`.

QQBot has been the primary target during development. Other platforms may need
adapter-specific validation, especially for group mention metadata and outbound
group-message permissions.

## Development Checks

Useful local checks:

```bash
python3 -m py_compile __init__.py
git diff --check
```

Suggested smoke tests:

- Duplicate pending request: send two events from the same unapproved principal
  and verify only one admin notification is sent.
- Group trigger: enable group requests and verify a group event creates a
  request.
- Admin group command: verify `/pa help` in a group is rejected and not executed.
- Batch commands: verify batch approve, alias, revoke, ignore, and deny paths.

## Privacy Notes

Do not put real user IDs, OpenIDs, API keys, tokens, server addresses, or
deployment-specific secrets in public documentation. Use placeholders such as
`qqbot:YOUR_OPENID` and `qqbot:USER_ID`.
