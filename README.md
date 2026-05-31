# pairing-admin

Language: **English** | [简体中文](README.zh-CN.md)

`pairing-admin` adds a chat-based approval flow in front of Hermes.

When Hermes is not open to every user, unknown users are normally blocked before
they can talk to the bot. With this plugin, an unknown user can send a message,
the plugin creates a short request code, and an admin can approve or deny that
request from chat:

```text
/pa approve ABC123 Alice
```

This is useful when you want to keep Hermes allowlisting enabled, but still let
friends, group members, or users from other messaging platforms request access
without editing `.env` by hand.

The plugin runs as a `pre_gateway_dispatch` hook. It handles eligible
unapproved users before Hermes' normal authorization flow, while staying
independent from official Hermes platform adapters.

## What It Does

- Turns messages from unapproved users into pending access requests.
- Sends request details to configured admins without consuming model tokens.
- Lets admins approve, deny, ignore, revoke, block, and unblock users from chat.
- Supports batch approve, batch deny, batch ignore, batch revoke, and batch alias
  operations.
- Stores member remarks grouped by platform, so `/pa users` is readable.
- Supports optional group-chat request intake while keeping admin actions DM-only.
- Deduplicates repeat messages from the same pending user, so admins only get
  one first-create notification per pending code.
- Sends lightweight pending-request reminders on a configurable interval.
- Automatically ignores stale pending requests after a configurable timeout.
- Keeps access authorization in Hermes' built-in pairing store.

## When To Use It

Use `pairing-admin` when you run a Hermes bot that should stay private or
semi-private, but you do not want every new user to require a manual config
edit.

Good fits:

- A personal Hermes bot shared with a few friends.
- A QQBot or group-facing bot where new users should request access before using
  the bot.
- A bot deployed across multiple messaging platforms, where one admin should be
  able to approve requests from any configured admin platform.
- A setup where Hermes allowlisting stays enabled, but approved users can be
  added through chat commands instead of `.env` edits and restarts.
- A lightweight member-management workflow where admins need aliases, revoke,
  block, pending reminders, and stale request cleanup.
- A token-conscious deployment where admission notices should be handled by the
  plugin instead of the model.

It is not meant to be a public self-service registration system. Every request
still needs admin review unless you choose to approve it. It also does not prove
a user's real-world identity; it only works with the stable user IDs provided by
the messaging platform adapter.

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

### 1. Find Your Hermes Home

The plugin must be installed under the Hermes home directory used by the running
Hermes gateway process.

By default this is usually:

```text
~/.hermes
```

If you set `HERMES_HOME`, use that value instead:

```bash
echo "$HERMES_HOME"
```

For the commands below, set a shell variable first. This keeps the examples safe
even when `HERMES_HOME` is not already exported:

```bash
export HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
```

The final plugin path should be:

```text
$HERMES_HOME/plugins/pairing-admin
```

If Hermes runs in Docker, first find which host directory is mounted as Hermes'
home inside the container.

Find the container name:

```bash
docker ps
```

Then inspect its mounts:

```bash
docker inspect HERMES_CONTAINER_NAME --format '{{range .Mounts}}{{println .Source "->" .Destination}}{{end}}'
```

Look for the line whose right side is the Hermes home inside the container,
usually something like `/home/hermes/.hermes`, `/root/.hermes`, or `/app/.hermes`.
Install the plugin under the left side of that line.

Example output:

```text
/srv/hermes-data -> /home/hermes/.hermes
```

This means the host directory is `/srv/hermes-data`, so install the plugin here:

```text
/srv/hermes-data/plugins/pairing-admin
```

Hermes inside the container will see that same plugin here:

```text
/home/hermes/.hermes/plugins/pairing-admin
```

If the mount points to a named Docker volume instead of a normal host path, the
simplest option is to copy or clone the plugin from inside the container using
the container's own `HERMES_HOME`.

### 2. Download The Plugin

Install from GitHub:

```bash
mkdir -p "$HERMES_HOME/plugins"
git clone https://github.com/Eridani075/pairing-admin.git "$HERMES_HOME/plugins/pairing-admin"
```

If the target directory already exists, update it instead:

```bash
cd "$HERMES_HOME/plugins/pairing-admin"
git pull
```

Manual install is also fine. Copy the repository contents into:

```text
$HERMES_HOME/plugins/pairing-admin
```

After installation, the directory should contain at least:

```text
__init__.py
plugin.yaml
README.md
README.zh-CN.md
```

### 3. Configure Admins

Add the plugin settings to `$HERMES_HOME/.env`, or to the process environment
used to start Hermes.

Minimal QQBot example:

```env
PAIRING_ADMIN_ADMINS=qqbot:YOUR_OPENID
PAIRING_ADMIN_PLATFORMS=qqbot
PAIRING_ADMIN_NOTIFY_ADMINS=true
PAIRING_ADMIN_NOTIFY_TARGETS=qqbot
QQ_ALLOW_ALL_USERS=false
```

Replace `YOUR_OPENID` with the admin user's platform ID. For QQBot this is the
admin OpenID. For another platform, use that adapter's stable user ID and the
matching platform name, for example `telegram:ADMIN_USER_ID`.

Do not use `PAIRING_ADMIN_ADMINS=*` on a public bot unless you intentionally want
every user to be able to approve requests.

### 4. Enable The Plugin

Enable the plugin:

```bash
hermes plugins enable pairing-admin
```

If Hermes reports that the plugin cannot be found, re-check that the plugin is
inside the same `$HERMES_HOME/plugins` directory used by the running gateway.

### 5. Restart Hermes

Restart the Hermes gateway after installing the plugin, changing plugin code, or
changing `.env`.

The exact restart command depends on how Hermes is deployed. Examples:

```bash
docker compose restart hermes
```

```bash
systemctl restart hermes
```

If Hermes runs in a Docker container and the `hermes` CLI is only available
inside that container, run the enable command through your container runtime, for
example:

```bash
docker compose exec hermes hermes plugins enable pairing-admin
```

### 6. Verify The Install

From an admin DM, send:

```text
/pa help
```

Expected result: the bot replies with the `pairing-admin commands` help text.

Then test the approval flow:

1. Send a message from an unapproved test user.
2. Confirm the admin receives a `Pairing request CODE` message.
3. Approve it from an admin DM:

```text
/pa approve CODE TestUser
```

4. Confirm the test user can now talk to Hermes.

If the admin does not receive a request, check `PAIRING_ADMIN_ADMINS`,
`PAIRING_ADMIN_NOTIFY_TARGETS`, `PAIRING_ADMIN_PLATFORMS`, and whether the
platform adapter is actually forwarding that user's message to Hermes.

### 7. Update Or Remove

To update:

```bash
cd "$HERMES_HOME/plugins/pairing-admin"
git pull
```

Restart Hermes after updating.

To remove the plugin, disable it if your Hermes install supports plugin
disablement, then delete the plugin directory and restart Hermes:

```bash
rm -rf "$HERMES_HOME/plugins/pairing-admin"
```

Removing the plugin does not automatically revoke users already approved in
Hermes' pairing store.

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

The plugin is gateway-level and is not hard-coded to QQBot, but the current
implementation has only been tested with the Hermes QQBot adapter. Other
platforms should be treated as adapter-compatible in design, but unverified until
you run the smoke tests below on that platform.

For another platform adapter to work, it should provide these event fields:

- `event.text`: message text used for commands, request messages, and mention
  marker matching.
- `event.source.platform`: platform name. This must match values used in
  `PAIRING_ADMIN_PLATFORMS`, `PAIRING_ADMIN_ADMINS`, and
  `PAIRING_ADMIN_NOTIFY_TARGETS`.
- `event.source.user_id`: stable user identity on that platform.
- `event.source.chat_id`: destination used for replies and request
  acknowledgements.
- `event.source.chat_type`: one of `c2c`, `dm`, or `private` for DMs; one of
  `group`, `guild`, `channel`, `group_at_message`, or `group_message` for group
  contexts.
- `event.source.user_name`: optional display name. If absent, requests show
  `user: (unknown)` and admins can add an alias while approving.

The adapter must also expose `send(chat_id, content)` through Hermes'
`gateway.adapters`. Admin notifications, applicant acknowledgements, approval
notices, denial notices, and command responses all use that send path.

Minimal configuration for a non-QQBot adapter:

```env
PAIRING_ADMIN_ADMINS=telegram:ADMIN_USER_ID
PAIRING_ADMIN_PLATFORMS=telegram
PAIRING_ADMIN_NOTIFY_TARGETS=telegram
```

Multi-platform example:

```env
PAIRING_ADMIN_ADMINS=qqbot:QQ_ADMIN_OPENID,telegram:TG_ADMIN_USER_ID
PAIRING_ADMIN_PLATFORMS=qqbot,telegram
PAIRING_ADMIN_NOTIFY_TARGETS=telegram
```

In the multi-platform example, both admins can approve requests from managed
platforms, but PA notifications are only sent to Telegram.

Group request support depends on adapter behavior:

- Use `PAIRING_ADMIN_GROUP_TRIGGER=mention` when the adapter forwards normal
  group messages and the plugin must detect whether the bot was mentioned. Set
  `PAIRING_ADMIN_BOT_MENTIONS` and, when available, `PAIRING_ADMIN_BOT_ID`.
- Use `PAIRING_ADMIN_GROUP_TRIGGER=received` when the adapter already filters
  group events so Hermes only receives bot-directed messages.
- Use `PAIRING_ADMIN_GROUP_TRIGGER=always` only when every group event received
  by Hermes should be treated as a PA request attempt.

Before marking another adapter as supported, verify at least:

1. An unapproved DM creates one pending request and notifies an admin.
2. Repeated messages from the same pending user reuse the same code.
3. `/pa approve CODE` from an admin DM grants access.
4. `/pa users platform` lists the approved user.
5. If group requests are enabled, a bot-directed group message creates a request.
6. If the platform allows group replies, the applicant receives the lightweight
   acknowledgement; if not, request creation can still work while group sending
   fails at the adapter/platform permission layer.

## Contributing

Forks and PRs are welcome, especially for adapter testing beyond QQBot.

If you test another Hermes platform adapter, please open a PR with:

- The adapter/platform name and Hermes version you tested.
- The event fields exposed by that adapter, especially `source.platform`,
  `source.user_id`, `source.chat_id`, and `source.chat_type`.
- Whether DM requests, admin commands, approval, revocation, and reminders work.
- Whether group request intake works, and which `PAIRING_ADMIN_GROUP_TRIGGER`
  mode is required.
- Any adapter-specific permission limitations, such as platforms that can create
  group requests but cannot send group replies.

Small documentation-only PRs that confirm a platform's status are useful. Code
changes should avoid modifying official Hermes adapters unless the adapter
itself has a real bug; platform-specific behavior should usually be documented
or handled inside this plugin.

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
