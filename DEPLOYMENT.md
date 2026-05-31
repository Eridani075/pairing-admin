# Deployment Notes

This file is intentionally generic. Keep host names, real paths, user IDs,
OpenIDs, tokens, and operator-specific history out of versioned documentation.

For full plugin usage, read [README.md](README.md). For Chinese documentation,
read [README.zh-CN.md](README.zh-CN.md).

The current implementation has only been tested with the Hermes QQBot adapter.
For other platform adapters, follow the adapter requirements and smoke tests in
the README before treating that platform as supported.

## Target Layout

Install the plugin under the Hermes user plugin directory:

```text
$HERMES_HOME/plugins/pairing-admin
```

Required files:

```text
__init__.py
plugin.yaml
README.md
README.zh-CN.md
```

Local-only notes, test artifacts, and handoff files should stay untracked.

## Environment

Minimal environment:

```env
PAIRING_ADMIN_ADMINS=qqbot:YOUR_OPENID
PAIRING_ADMIN_PLATFORMS=qqbot
PAIRING_ADMIN_NOTIFY_ADMINS=true
PAIRING_ADMIN_NOTIFY_TARGETS=qqbot
```

Common optional settings:

```env
PAIRING_ADMIN_ALLOW_GROUP_REQUESTS=false
PAIRING_ADMIN_GROUP_TRIGGER=mention
PAIRING_ADMIN_BOT_MENTIONS=@YourBotName
PAIRING_ADMIN_REMIND_ADMINS=true
PAIRING_ADMIN_REMIND_AFTER_SECONDS=600
PAIRING_ADMIN_REMIND_INTERVAL_SECONDS=1800
PAIRING_ADMIN_REMIND_CHECK_SECONDS=60
PAIRING_ADMIN_AUTO_IGNORE_AFTER_SECONDS=86400
```

Use `PAIRING_ADMIN_AUTO_IGNORE_AFTER_SECONDS=0` to disable automatic ignoring.
Use `PAIRING_ADMIN_NOTIFY_TARGETS` to avoid notifying the same admin on every
platform they have configured.

## Enable And Restart

Enable the plugin from the Hermes runtime:

```bash
hermes plugins enable pairing-admin
```

Restart the Hermes gateway after changing plugin code or environment. The exact
restart command depends on the deployment method.

## Verification

Run local syntax and whitespace checks before deploying:

```bash
python3 -m py_compile __init__.py
git diff --check
```

Suggested smoke test after deployment:

1. Send a DM from an unapproved test user and confirm one admin notification.
2. Send another message from the same pending user and confirm the same code is
   reused without another first-create admin notification.
3. Approve the code from an admin DM.
4. Confirm the test user can talk to Hermes.
5. If group requests are enabled, send a bot-directed group message and confirm
   a request is created.

## Rollback

Disable the plugin or remove it from the Hermes user plugin directory, then
restart the gateway. Approved access already written to Hermes' pairing store is
not automatically removed when the plugin is disabled.
