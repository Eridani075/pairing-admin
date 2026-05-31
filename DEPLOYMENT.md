# Deployment Notes

This file is a short deployment checklist. For the full step-by-step install
guide, read [README.md](README.md#installation) or
[README.zh-CN.md](README.zh-CN.md#安装).

The current implementation has only been tested with the Hermes QQBot adapter.
For other platform adapters, follow the adapter requirements and smoke tests in
the README before treating that platform as supported.

## Install

The final plugin directory must be:

```text
$HERMES_HOME/plugins/pairing-admin
```

For a host install, this usually means:

```bash
export HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
mkdir -p "$HERMES_HOME/plugins"
git clone https://github.com/Eridani075/pairing-admin.git "$HERMES_HOME/plugins/pairing-admin"
```

For Docker, first decide where the container's Hermes home lives:

```bash
docker ps
docker inspect HERMES_CONTAINER_NAME --format '{{range .Mounts}}{{println .Source "->" .Destination}}{{end}}'
```

If you see:

```text
/srv/hermes-data -> /home/hermes/.hermes
```

install to:

```text
/srv/hermes-data/plugins/pairing-admin
```

The container sees it at:

```text
/home/hermes/.hermes/plugins/pairing-admin
```

## Environment

Minimal QQBot example:

```env
PAIRING_ADMIN_ADMINS=qqbot:YOUR_OPENID
PAIRING_ADMIN_PLATFORMS=qqbot
PAIRING_ADMIN_NOTIFY_ADMINS=true
PAIRING_ADMIN_NOTIFY_TARGETS=qqbot
QQ_ALLOW_ALL_USERS=false
```

Common optional settings:

```env
PAIRING_ADMIN_ALLOW_GROUP_REQUESTS=false
PAIRING_ADMIN_GROUP_TRIGGER=mention
PAIRING_ADMIN_BOT_MENTIONS=@YourBotName
PAIRING_ADMIN_REMIND_ADMINS=true
PAIRING_ADMIN_REMIND_AFTER_SECONDS=600
PAIRING_ADMIN_REMIND_INTERVAL_SECONDS=1800
PAIRING_ADMIN_AUTO_IGNORE_AFTER_SECONDS=86400
```

## Enable And Restart

Enable the plugin:

```bash
hermes plugins enable pairing-admin
```

If Hermes runs in Docker and the CLI only exists inside the container:

```bash
docker exec -it HERMES_CONTAINER_NAME hermes plugins enable pairing-admin
```

Restart Hermes after changing plugin code or environment:

```bash
docker restart HERMES_CONTAINER_NAME
```

```bash
docker compose restart hermes
```

```bash
systemctl restart hermes
```

## Verification

From an admin DM, send:

```text
/pa help
```

Then send a message from an unapproved test user and approve the request:

```text
/pa approve CODE TestUser
```

## Rollback

Remove the plugin directory and restart Hermes:

```bash
rm -rf "$HERMES_HOME/plugins/pairing-admin"
```

Approved access already written to Hermes' pairing store is not automatically
removed when the plugin is disabled or deleted.
