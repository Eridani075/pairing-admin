"""Admin-mediated pairing workflow for Hermes gateway platforms."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import time
from pathlib import Path
from typing import Any


PLUGIN_NAME = "pairing-admin"
STATE_VERSION = 1
DEFAULT_AUTO_IGNORE_AFTER_SECONDS = 24 * 60 * 60
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
LOGGER = logging.getLogger(__name__)
_REMINDER_TASK: asyncio.Task[Any] | None = None
_DOTENV_CACHE: dict[str, str] | None = None


def _hermes_home() -> Path:
    try:
        from hermes_constants import get_hermes_home

        return Path(get_hermes_home())
    except Exception:
        return Path(os.getenv("HERMES_HOME", "~/.hermes")).expanduser()


def _state_dir() -> Path:
    return _hermes_home() / "pairing-admin"


def _state_path() -> Path:
    return _state_dir() / "state.json"


def _now() -> float:
    return time.time()


def _load_dotenv_values() -> dict[str, str]:
    global _DOTENV_CACHE
    if _DOTENV_CACHE is not None:
        return _DOTENV_CACHE

    values: dict[str, str] = {}
    path = _hermes_home() / ".env"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        _DOTENV_CACHE = values
        return values

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value

    _DOTENV_CACHE = values
    return values


def _config_value(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value is not None:
        return value
    return _load_dotenv_values().get(name, default)


def _platform_value(platform: Any) -> str:
    return str(getattr(platform, "value", platform) or "").strip()


def _principal(platform: str, user_id: str | None) -> str:
    return f"{platform}:{str(user_id or '').strip()}"


def _split_principal(value: str) -> tuple[str, str]:
    raw = str(value or "").strip()
    if ":" not in raw:
        return "", raw
    platform, user_id = raw.split(":", 1)
    return platform.strip(), user_id.strip()


def _parse_csv_env(name: str) -> set[str]:
    raw = _config_value(name)
    return {item.strip() for item in raw.split(",") if item.strip()}


def _int_env(name: str, default: int, minimum: int = 0) -> int:
    try:
        value = int(_config_value(name, str(default)).strip())
    except (TypeError, ValueError):
        return default
    return max(minimum, value)


def _managed_platforms() -> set[str]:
    configured = _parse_csv_env("PAIRING_ADMIN_PLATFORMS")
    return configured or {"qqbot"}


def _admin_principals() -> set[str]:
    admins = _parse_csv_env("PAIRING_ADMIN_ADMINS")
    legacy = _config_value("PAIRING_ADMIN_QQ_ADMINS")
    for item in legacy.split(","):
        item = item.strip()
        if item:
            admins.add(item if ":" in item else f"qqbot:{item}")
    return admins


def _notify_admins_enabled() -> bool:
    return _config_value("PAIRING_ADMIN_NOTIFY_ADMINS", "true").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _notify_targets_filter() -> set[str]:
    return _parse_csv_env("PAIRING_ADMIN_NOTIFY_TARGETS")


def _group_requests_enabled() -> bool:
    return _config_value("PAIRING_ADMIN_ALLOW_GROUP_REQUESTS", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _group_trigger_mode() -> str:
    mode = _config_value("PAIRING_ADMIN_GROUP_TRIGGER", "mention").strip().lower()
    if mode in {"mention", "received", "always"}:
        return mode
    return "mention"


def _bot_mentions() -> set[str]:
    return _parse_csv_env("PAIRING_ADMIN_BOT_MENTIONS")


def _reminders_enabled() -> bool:
    return _config_value("PAIRING_ADMIN_REMIND_ADMINS", "true").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _remind_after_seconds() -> int:
    return _int_env("PAIRING_ADMIN_REMIND_AFTER_SECONDS", 10 * 60, 0)


def _remind_interval_seconds() -> int:
    return _int_env("PAIRING_ADMIN_REMIND_INTERVAL_SECONDS", 30 * 60, 60)


def _remind_check_seconds() -> int:
    return _int_env("PAIRING_ADMIN_REMIND_CHECK_SECONDS", 60, 10)


def _configured_auto_ignore_after_seconds() -> int:
    return _int_env(
        "PAIRING_ADMIN_AUTO_IGNORE_AFTER_SECONDS",
        DEFAULT_AUTO_IGNORE_AFTER_SECONDS,
        0,
    )


def _auto_ignore_after_seconds(state: dict[str, Any] | None = None) -> int:
    if state is not None and "auto_ignore_after_seconds" in state:
        try:
            return max(0, int(state.get("auto_ignore_after_seconds") or 0))
        except (TypeError, ValueError):
            return 0
    return _configured_auto_ignore_after_seconds()


def _load_state() -> dict[str, Any]:
    path = _state_path()
    if not path.exists():
        return {
            "version": STATE_VERSION,
            "requests": {},
            "blocked": {},
            "members": {},
            "ignored": {},
            "aliases": {},
            "audit": [],
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    data.setdefault("version", STATE_VERSION)
    data.setdefault("requests", {})
    data.setdefault("blocked", {})
    data.setdefault("members", {})
    data.setdefault("ignored", {})
    data.setdefault("aliases", {})
    data.setdefault("audit", [])
    return data


def _save_state(state: dict[str, Any]) -> None:
    _state_dir().mkdir(parents=True, exist_ok=True)
    path = _state_path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _append_audit(state: dict[str, Any], action: str, **fields: Any) -> None:
    audit = state.setdefault("audit", [])
    audit.append({"ts": _now(), "action": action, **fields})
    del audit[:-200]


def _ignore_request(
    state: dict[str, Any],
    code: str,
    item: dict[str, Any],
    *,
    ignored_by: str,
    reason: str,
) -> str:
    principal = item.get("principal") or _principal(item.get("platform"), item.get("user_id"))
    state.setdefault("ignored", {})[principal] = {
        "code": code,
        "ignored_at": _now(),
        "ignored_by": ignored_by,
        "reason": reason,
    }
    _append_audit(
        state,
        "ignore",
        admin=ignored_by,
        principal=principal,
        code=code,
        reason=reason,
    )
    return principal


def _clean_expired_requests(state: dict[str, Any]) -> None:
    requests = state.setdefault("requests", {})
    auto_ignore_after = _auto_ignore_after_seconds(state)
    now = _now()
    for code, item in list(requests.items()):
        if not isinstance(item, dict):
            requests.pop(code, None)
            continue
        if auto_ignore_after <= 0:
            continue
        created_at = float(item.get("created_at") or now)
        if now - created_at < auto_ignore_after:
            continue
        requests.pop(code, None)
        _ignore_request(
            state,
            code,
            item,
            ignored_by="system:auto-ignore",
            reason="expired",
        )


def _members_for_platform(state: dict[str, Any], platform: str) -> dict[str, Any]:
    members = state.setdefault("members", {})
    if not isinstance(members, dict):
        members = {}
        state["members"] = members
    platform_members = members.setdefault(platform, {})
    if not isinstance(platform_members, dict):
        platform_members = {}
        members[platform] = platform_members
    return platform_members


def _member_entry(
    state: dict[str, Any],
    platform: str,
    user_id: str,
    *,
    create: bool = False,
) -> dict[str, Any] | None:
    platform_members = _members_for_platform(state, platform)
    entry = platform_members.get(user_id)
    if isinstance(entry, dict):
        return entry
    if not create:
        return None
    entry = {
        "platform": platform,
        "user_id": user_id,
        "principal": _principal(platform, user_id),
    }
    platform_members[user_id] = entry
    return entry


def _alias_for(state: dict[str, Any], platform: str, user_id: str, fallback: str = "") -> str:
    entry = _member_entry(state, platform, user_id)
    if entry and entry.get("alias"):
        return str(entry.get("alias") or "")
    return str(state.get("aliases", {}).get(_principal(platform, user_id)) or fallback or "")


def _record_member(
    state: dict[str, Any],
    platform: str,
    user_id: str,
    *,
    alias: str = "",
    user_name: str = "",
    approved_by: str = "",
    approved_at: float | None = None,
) -> None:
    entry = _member_entry(state, platform, user_id, create=True)
    if entry is None:
        return
    entry["platform"] = platform
    entry["user_id"] = user_id
    entry["principal"] = _principal(platform, user_id)
    if user_name:
        entry["user_name"] = user_name
    if alias:
        entry["alias"] = alias
        state.setdefault("aliases", {})[_principal(platform, user_id)] = alias
    elif state.get("aliases", {}).get(_principal(platform, user_id)) and not entry.get("alias"):
        entry["alias"] = state["aliases"][_principal(platform, user_id)]
    entry.setdefault("approved_at", approved_at or _now())
    if approved_by:
        entry["approved_by"] = approved_by


def _set_member_alias(state: dict[str, Any], platform: str, user_id: str, alias: str) -> None:
    entry = _member_entry(state, platform, user_id, create=True)
    if entry is not None:
        entry["alias"] = alias
    state.setdefault("aliases", {})[_principal(platform, user_id)] = alias


def _remove_member(state: dict[str, Any], platform: str, user_id: str) -> None:
    platform_members = _members_for_platform(state, platform)
    platform_members.pop(user_id, None)
    if not platform_members:
        state.setdefault("members", {}).pop(platform, None)
    state.setdefault("aliases", {}).pop(_principal(platform, user_id), None)


def _group_approved_users(
    state: dict[str, Any],
    users: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in users:
        platform = str(item.get("platform") or "")
        user_id = str(item.get("user_id") or "")
        if not platform or not user_id:
            continue
        enriched = dict(item)
        enriched["alias"] = _alias_for(state, platform, user_id, item.get("user_name") or "")
        grouped.setdefault(platform, []).append(enriched)
    return grouped


def _request_code(value: str) -> str:
    return str(value or "").strip().upper()


def _looks_like_request_code(value: str) -> bool:
    code = _request_code(value)
    return len(code) == 6 and all(char in CODE_ALPHABET for char in code)


def _parse_approve_specs(
    args: list[str],
    requests: dict[str, Any],
) -> list[tuple[str, str]]:
    if not args:
        return []

    if args[0].lower() == "all":
        return [(code, "") for code in sorted(requests)]

    if any("=" in token for token in args):
        if "=" in args[0] and not any("=" in token for token in args[1:]):
            raw_code, _, raw_alias = args[0].partition("=")
            if len(args) > 1 and not all(_looks_like_request_code(token) for token in args[1:]):
                return [(_request_code(raw_code), " ".join([raw_alias, *args[1:]]).strip())]

        specs: list[tuple[str, str]] = []
        for token in args:
            raw_code, sep, raw_alias = token.partition("=")
            specs.append((_request_code(raw_code), raw_alias.strip() if sep else ""))
        return specs

    if len(args) == 1:
        return [(_request_code(args[0]), "")]

    first = _request_code(args[0])
    rest_contains_pending = any(_request_code(token) in requests for token in args[1:])
    rest_looks_like_codes = all(_looks_like_request_code(token) for token in args[1:])
    if first in requests and not rest_contains_pending and not rest_looks_like_codes:
        return [(first, " ".join(args[1:]).strip())]

    return [(_request_code(token), "") for token in args]


def _parse_codes(args: list[str], requests: dict[str, Any]) -> list[str]:
    if args and args[0].lower() == "all":
        return sorted(requests)
    return [_request_code(arg) for arg in args]


def _format_age(seconds: float) -> str:
    seconds = max(0, int(seconds))
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    rest = minutes % 60
    if hours < 48:
        return f"{hours}h{rest:02d}m"
    days = hours // 24
    return f"{days}d{hours % 24}h"


def _format_duration(seconds: int) -> str:
    if seconds <= 0:
        return "off"
    return _format_age(seconds)


def _pending_request_items(state: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    items: list[tuple[str, dict[str, Any]]] = []
    for code, item in state.get("requests", {}).items():
        if isinstance(item, dict):
            items.append((code, item))
    return sorted(items, key=lambda entry: float(entry[1].get("created_at") or 0))


def _format_pending_reminder(state: dict[str, Any]) -> str:
    now = _now()
    items = _pending_request_items(state)
    lines = [f"Pending pairing requests need review: {len(items)}"]
    for code, item in items[:10]:
        platform = item.get("platform") or "unknown"
        user_id = item.get("user_id") or ""
        user_name = item.get("user_name") or "(unknown)"
        age = _format_age(now - float(item.get("created_at") or now))
        lines.append(f"- {code}: {platform}:{user_id} {user_name} ({age})")
    if len(items) > 10:
        lines.append(f"... and {len(items) - 10} more")
    lines.append("approve: /pa approve CODE | ignore: /pa ignore CODE | deny: /pa deny CODE")
    return "\n".join(lines)


def _format_config(state: dict[str, Any]) -> str:
    return (
        "pairing-admin config:\n"
        f"auto-ignore-after: {_format_duration(_auto_ignore_after_seconds(state))}\n"
        f"group-requests: {'on' if _group_requests_enabled() else 'off'}\n"
        f"group-trigger: {_group_trigger_mode()}\n"
        f"remind-admins: {'on' if _reminders_enabled() else 'off'}\n"
        f"remind-after: {_format_duration(_remind_after_seconds())}\n"
        f"remind-interval: {_format_duration(_remind_interval_seconds())}\n"
        f"notify-targets: {', '.join(sorted(_notify_targets_filter())) or '(all admins)'}"
    )


def _parse_duration_seconds(value: str) -> int | None:
    raw = str(value or "").strip().lower()
    if raw in {"off", "disable", "disabled", "never", "none", "0"}:
        return 0
    if raw.endswith("h"):
        number = raw[:-1]
        multiplier = 60 * 60
    elif raw.endswith("d"):
        number = raw[:-1]
        multiplier = 24 * 60 * 60
    elif raw.endswith("m"):
        number = raw[:-1]
        multiplier = 60
    elif raw.endswith("s"):
        number = raw[:-1]
        multiplier = 1
    else:
        number = raw
        multiplier = 1
    try:
        return max(0, int(float(number) * multiplier))
    except (TypeError, ValueError):
        return None


def _maybe_remind_pending(state: dict[str, Any], gateway: Any, *, force: bool = False) -> bool:
    if not _notify_admins_enabled() or not _reminders_enabled():
        return False

    items = _pending_request_items(state)
    if not items:
        return False

    now = _now()
    if not force:
        remind_after = _remind_after_seconds()
        if not any(now - float(item.get("created_at") or now) >= remind_after for _, item in items):
            return False
        last_reminded_at = float(state.get("last_pending_reminder_at") or 0)
        if now - last_reminded_at < _remind_interval_seconds():
            return False

    targets = _admin_targets()
    if not targets:
        return False

    message = _format_pending_reminder(state)
    for admin_platform, admin_chat_id in targets:
        _schedule_send(gateway, admin_platform, admin_chat_id, message)

    state["last_pending_reminder_at"] = now
    state["last_pending_reminder_count"] = len(items)
    return True


async def _reminder_loop(gateway: Any) -> None:
    while True:
        await asyncio.sleep(_remind_check_seconds())
        try:
            state = _load_state()
            _clean_expired_requests(state)
            _maybe_remind_pending(state, gateway)
            _save_state(state)
        except asyncio.CancelledError:
            raise
        except Exception:
            LOGGER.exception("pairing-admin pending reminder failed")


def _ensure_reminder_task(gateway: Any) -> None:
    global _REMINDER_TASK
    if not _notify_admins_enabled() or not _reminders_enabled():
        return
    if _REMINDER_TASK is not None and not _REMINDER_TASK.done():
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    _REMINDER_TASK = loop.create_task(_reminder_loop(gateway))


def _new_code(existing: dict[str, Any]) -> str:
    while True:
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))
        if code not in existing:
            return code


def _is_admin(source: Any) -> bool:
    platform = _platform_value(getattr(source, "platform", ""))
    user_id = getattr(source, "user_id", None)
    principal = _principal(platform, user_id)
    admins = _admin_principals()
    return principal in admins or "*" in admins


def _is_managed(source: Any) -> bool:
    platform = _platform_value(getattr(source, "platform", ""))
    return platform in _managed_platforms() or "*" in _managed_platforms()


def _is_dm(source: Any) -> bool:
    return str(getattr(source, "chat_type", "") or "").lower() in {"c2c", "dm", "private"}


def _is_group_chat(source: Any) -> bool:
    chat_type = str(getattr(source, "chat_type", "") or "").lower()
    return chat_type in {"group", "guild", "channel", "group_at_message", "group_message"}


def _text_mentions_bot(text: str) -> bool:
    lowered = text.lower()
    for marker in _bot_mentions():
        marker = marker.strip()
        if marker and marker.lower() in lowered:
            return True
    return False


def _iter_values(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _event_mentions_bot(event: Any, gateway: Any) -> bool:
    text = str(getattr(event, "text", "") or "")
    if _text_mentions_bot(text):
        return True

    bot_ids = {
        str(item).strip()
        for item in [
            _config_value("PAIRING_ADMIN_BOT_ID"),
            _config_value("QQ_BOT_ID"),
            _config_value("QQBOT_BOT_ID"),
            getattr(gateway, "bot_id", ""),
            getattr(getattr(event, "source", None), "bot_id", ""),
        ]
        if str(item or "").strip()
    }

    metadata = getattr(event, "metadata", None) or getattr(event, "raw", None) or {}
    candidates: list[Any] = []
    for obj in [event, getattr(event, "source", None), metadata]:
        for attr in (
            "mentions",
            "mention_user_ids",
            "mentioned_user_ids",
            "at_user_ids",
            "at_users",
            "message_mentions",
        ):
            if isinstance(obj, dict):
                candidates.extend(_iter_values(obj.get(attr)))
            else:
                candidates.extend(_iter_values(getattr(obj, attr, None)))

    for candidate in candidates:
        if isinstance(candidate, dict):
            values = candidate.values()
        else:
            values = [
                candidate,
                getattr(candidate, "id", None),
                getattr(candidate, "user_id", None),
                getattr(candidate, "openid", None),
            ]
        for value in values:
            if str(value or "").strip() in bot_ids:
                return True

    return False


def _admin_reply_chat_id(source: Any) -> str:
    if _is_dm(source):
        return str(getattr(source, "chat_id", "") or getattr(source, "user_id", "") or "").strip()
    return str(getattr(source, "user_id", "") or getattr(source, "chat_id", "") or "").strip()


def _should_handle_source(event: Any, gateway: Any) -> bool:
    source = getattr(event, "source", None)
    if source is None or not _is_managed(source):
        return False
    if _is_dm(source):
        return True
    if not _is_group_chat(source) or not _group_requests_enabled():
        return False
    mode = _group_trigger_mode()
    return mode in {"received", "always"} or _event_mentions_bot(event, gateway)


def _is_approved(gateway: Any, platform: str, user_id: str) -> bool:
    try:
        return bool(gateway.pairing_store.is_approved(platform, user_id))
    except Exception:
        return False


def _approve_user(gateway: Any, platform: str, user_id: str, user_name: str = "") -> None:
    store = getattr(gateway, "pairing_store", None)
    if store is None:
        raise RuntimeError("gateway pairing_store is unavailable")
    lock = getattr(store, "_lock", None)
    if lock is None:
        store._approve_user(platform, user_id, user_name)
        return
    with lock:
        store._approve_user(platform, user_id, user_name)


def _revoke_user(gateway: Any, platform: str, user_id: str) -> bool:
    store = getattr(gateway, "pairing_store", None)
    if store is None:
        return False
    return bool(store.revoke(platform, user_id))


def _approved_users(gateway: Any, platform: str | None = None) -> list[dict[str, Any]]:
    store = getattr(gateway, "pairing_store", None)
    if store is None:
        return []
    return list(store.list_approved(platform))


async def _send(gateway: Any, platform: str, chat_id: str, content: str) -> None:
    adapter = getattr(gateway, "adapters", {}).get(getattr(_platform_enum(platform), "value", None))
    if adapter is None:
        adapter = getattr(gateway, "adapters", {}).get(_platform_enum(platform))
    if adapter is None:
        adapters = getattr(gateway, "adapters", {})
        for key, value in adapters.items():
            if _platform_value(key) == platform:
                adapter = value
                break
    if adapter is None:
        return
    result = adapter.send(chat_id, content)
    if asyncio.iscoroutine(result):
        await result


def _platform_enum(platform: str) -> Any:
    try:
        from gateway.config import Platform

        for item in Platform:
            if item.value == platform:
                return item
    except Exception:
        pass
    return platform


def _schedule_send(gateway: Any, platform: str, chat_id: str, content: str) -> None:
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_send(gateway, platform, chat_id, content))
    except RuntimeError:
        asyncio.run(_send(gateway, platform, chat_id, content))


def _admin_targets() -> list[tuple[str, str]]:
    targets: list[tuple[str, str]] = []
    filters = _notify_targets_filter()
    for principal in _admin_principals():
        if principal == "*":
            continue
        platform, user_id = _split_principal(principal)
        if platform and user_id:
            if filters and platform not in filters and principal not in filters:
                continue
            targets.append((platform, user_id))
    return targets


def _request_for_user(state: dict[str, Any], principal: str) -> tuple[str, dict[str, Any]] | None:
    for code, item in state.get("requests", {}).items():
        if isinstance(item, dict) and item.get("principal") == principal:
            return code, item
    return None


def _format_request(code: str, item: dict[str, Any]) -> str:
    user_name = item.get("user_name") or "(unknown)"
    platform = item.get("platform") or "unknown"
    user_id = item.get("user_id") or ""
    text = item.get("first_text") or ""
    if len(text) > 120:
        text = text[:117] + "..."
    return (
        f"Pairing request {code}\n"
        f"platform: {platform}\n"
        f"user: {user_name}\n"
        f"id: {user_id}\n"
        f"message: {text or '(empty)'}\n"
        f"approve: /pa approve {code} [alias]\n"
        f"ignore: /pa ignore {code}\n"
        f"deny: /pa deny {code}"
    )


def _help() -> str:
    return (
        "pairing-admin commands:\n"
        "/pa help - show this help text / 显示帮助\n"
        "/pa pending - list waiting requests / 查看待审批申请\n"
        "/pa config - show plugin settings / 查看插件配置\n"
        "/pa auto-ignore 24h|off - set pending auto-ignore / 设置申请自动忽略时间\n"
        "/pa users [platform] - list approved users grouped by platform / 按平台查看已批准用户\n"
        "/pa approve CODE [alias] - approve a request / 批准申请，可顺手加备注名\n"
        "/pa approve CODE1 CODE2 - approve multiple requests / 批量批准\n"
        "/pa approve CODE=alias CODE2=alias2 - batch approve with aliases / 批量批准并备注\n"
        "/pa approve all - approve all pending requests / 批量通过全部待审批\n"
        "/pa ignore CODE... - drop pending requests silently / 忽略申请，不通知申请人\n"
        "/pa deny CODE... - deny pending requests / 拒绝申请，会通知申请人\n"
        "/pa alias platform:user_id=alias ... - set member aliases / 批量设置成员备注\n"
        "/pa revoke platform:user_id ... - remove approved access / 批量移除已批准用户\n"
        "/pa delete platform:user_id ... - same as revoke / 批量删除成员授权\n"
        "/pa block platform:user_id [reason] - revoke and blacklist / 拉黑用户并移除访问权\n"
        "/pa unblock platform:user_id - remove from blacklist / 解除拉黑\n"
        "/pa blocked - list blacklisted users / 查看黑名单\n"
        "Shortcuts: 同意 CODE, 批准 CODE, 拒绝 CODE, 忽略 CODE"
    )


def _handle_admin_command(event: Any, gateway: Any) -> str | None:
    text = str(getattr(event, "text", "") or "").strip()
    if not text:
        return None

    if text.startswith("/pa"):
        parts = text.split()
        action = parts[1].lower() if len(parts) > 1 else "help"
        args = parts[2:]
    elif text.startswith(("同意", "批准", "通过")):
        action = "approve"
        args = text.split()[1:]
    elif text.startswith(("拒绝", "驳回")):
        action = "deny"
        args = text.split()[1:]
    elif text.startswith(("忽略", "无视")):
        action = "ignore"
        args = text.split()[1:]
    else:
        return None

    source = event.source
    admin = _principal(_platform_value(source.platform), source.user_id)
    state = _load_state()
    skip_initial_cleanup = action in {"auto-ignore", "autoignore", "ttl", "config", "settings"}
    if not skip_initial_cleanup:
        _clean_expired_requests(state)

    if action in {"help", "h"}:
        _save_state(state)
        return _help()

    if action in {"pending", "p"}:
        requests = _pending_request_items(state)
        _save_state(state)
        if not requests:
            return "No pending pairing requests."
        lines = ["Pending pairing requests:"]
        now = _now()
        for code, item in requests:
            age = _format_age(now - float(item.get("created_at") or now))
            lines.append(
                f"- {code}: {item.get('platform')}:{item.get('user_id')} "
                f"{item.get('user_name') or ''} ({age})"
            )
        return "\n".join(lines)

    if action in {"config", "settings"}:
        _save_state(state)
        return _format_config(state)

    if action in {"auto-ignore", "autoignore", "ttl"}:
        if not args:
            _save_state(state)
            return "Usage: /pa auto-ignore 24h | /pa auto-ignore off"
        seconds = _parse_duration_seconds(args[0])
        if seconds is None:
            _save_state(state)
            return "Use a duration like 30m, 24h, 7d, seconds, or off."
        state["auto_ignore_after_seconds"] = seconds
        _clean_expired_requests(state)
        _save_state(state)
        return f"Auto-ignore-after set to {_format_duration(seconds)}."

    if action in {"users", "u"}:
        platform = args[0] if args else None
        users = _approved_users(gateway, platform)
        if not users:
            return "No approved users."
        grouped = _group_approved_users(state, users)
        lines = ["Approved users:"]
        for platform_name in sorted(grouped):
            lines.append(f"[{platform_name}]")
            for item in sorted(grouped[platform_name], key=lambda x: str(x.get("user_id") or "")):
                user_id = str(item.get("user_id") or "")
                alias = str(item.get("alias") or "")
                suffix = f" ({alias})" if alias else ""
                lines.append(f"- {user_id}{suffix}")
        return "\n".join(lines)

    if action in {"blocked", "blacklist"}:
        blocked = state.get("blocked", {})
        if not blocked:
            return "Blacklist is empty."
        lines = ["Blocked users:"]
        for principal, item in sorted(blocked.items()):
            reason = ""
            if isinstance(item, dict) and item.get("reason"):
                reason = f" - {item.get('reason')}"
            lines.append(f"- {principal}{reason}")
        return "\n".join(lines)

    if action in {"approve", "allow", "a"}:
        if not args:
            return "Usage: /pa approve CODE [alias] | /pa approve CODE1 CODE2 | /pa approve all"

        requests = state.get("requests", {})
        specs = _parse_approve_specs(args, requests)

        approved: list[str] = []
        missing: list[str] = []
        malformed: list[str] = []
        for code, alias in specs:
            item = requests.pop(code, None)
            if not isinstance(item, dict):
                missing.append(code)
                continue
            platform = item.get("platform")
            user_id = item.get("user_id")
            user_name = alias or item.get("user_name") or ""
            if not platform or not user_id:
                malformed.append(code)
                continue
            principal = _principal(platform, user_id)
            state.get("blocked", {}).pop(principal, None)
            if alias:
                _set_member_alias(state, platform, user_id, alias)
            _approve_user(gateway, platform, user_id, user_name)
            _record_member(
                state,
                platform,
                user_id,
                alias=alias,
                user_name=item.get("user_name") or "",
                approved_by=admin,
            )
            _append_audit(state, "approve", admin=admin, principal=principal, code=code)
            _schedule_send(
                gateway,
                platform,
                item.get("chat_id") or user_id,
                "Your Hermes access was approved.",
            )
            approved.append(principal)

        _save_state(state)
        parts = []
        if approved:
            parts.append("Approved:\n" + "\n".join(f"- {p}" for p in approved))
        if missing:
            parts.append("Missing codes: " + ", ".join(missing))
        if malformed:
            parts.append("Malformed requests: " + ", ".join(malformed))
        return "\n\n".join(parts) if parts else "No requests approved."

    if action in {"alias", "rename", "note"}:
        if not args:
            return "Usage: /pa alias platform:user_id=alias ..."
        updated: list[str] = []
        invalid: list[str] = []
        if len(args) == 1 and "=" not in args[0]:
            invalid.append(args[0])
        elif len(args) > 1 and "=" not in args[0]:
            platform, user_id = _split_principal(args[0])
            alias = " ".join(args[1:]).strip()
            if platform and user_id and alias:
                _set_member_alias(state, platform, user_id, alias)
                _append_audit(state, "alias", admin=admin, principal=_principal(platform, user_id), alias=alias)
                updated.append(_principal(platform, user_id))
            else:
                invalid.append(" ".join(args))
        else:
            for token in args:
                principal_raw, sep, alias = token.partition("=")
                platform, user_id = _split_principal(principal_raw)
                alias = alias.strip()
                if not sep or not platform or not user_id or not alias:
                    invalid.append(token)
                    continue
                _set_member_alias(state, platform, user_id, alias)
                _append_audit(state, "alias", admin=admin, principal=_principal(platform, user_id), alias=alias)
                updated.append(_principal(platform, user_id))
        _save_state(state)
        parts = []
        if updated:
            parts.append("Aliases updated:\n" + "\n".join(f"- {p}" for p in updated))
        if invalid:
            parts.append("Invalid alias specs: " + ", ".join(invalid))
        return "\n\n".join(parts) if parts else "No aliases updated."

    if action in {"deny", "reject", "d"}:
        if not args:
            return "Usage: /pa deny CODE..."
        denied: list[str] = []
        missing: list[str] = []
        requests = state.get("requests", {})
        for code in _parse_codes(args, requests):
            item = requests.pop(code, None)
            if not isinstance(item, dict):
                missing.append(code)
                continue
            principal = item.get("principal") or _principal(item.get("platform"), item.get("user_id"))
            _append_audit(state, "deny", admin=admin, principal=principal, code=code)
            _schedule_send(
                gateway,
                item.get("platform"),
                item.get("chat_id") or item.get("user_id"),
                "Your Hermes access request was denied.",
            )
            denied.append(principal)
        _save_state(state)
        parts = []
        if denied:
            parts.append("Denied:\n" + "\n".join(f"- {p}" for p in denied))
        if missing:
            parts.append("Missing codes: " + ", ".join(missing))
        return "\n\n".join(parts) if parts else "No requests denied."

    if action in {"ignore", "skip"}:
        if not args:
            return "Usage: /pa ignore CODE..."
        ignored: list[str] = []
        missing: list[str] = []
        requests = state.get("requests", {})
        for code in _parse_codes(args, requests):
            item = requests.pop(code, None)
            if not isinstance(item, dict):
                missing.append(code)
                continue
            principal = _ignore_request(
                state,
                code,
                item,
                ignored_by=admin,
                reason="manual",
            )
            ignored.append(principal)
        _save_state(state)
        parts = []
        if ignored:
            parts.append("Ignored:\n" + "\n".join(f"- {p}" for p in ignored))
        if missing:
            parts.append("Missing codes: " + ", ".join(missing))
        return "\n\n".join(parts) if parts else "No requests ignored."

    if action in {"revoke", "remove", "rm", "delete", "del"}:
        if not args:
            return "Usage: /pa revoke platform:user_id ..."
        removed_items: list[str] = []
        not_found: list[str] = []
        invalid: list[str] = []
        for spec in args:
            platform, user_id = _split_principal(spec)
            if not platform or not user_id:
                invalid.append(spec)
                continue
            removed = _revoke_user(gateway, platform, user_id)
            principal = _principal(platform, user_id)
            _remove_member(state, platform, user_id)
            _append_audit(state, "revoke", admin=admin, principal=principal, removed=removed)
            if removed:
                removed_items.append(principal)
            else:
                not_found.append(principal)
        _save_state(state)
        parts = []
        if removed_items:
            parts.append("Revoked:\n" + "\n".join(f"- {p}" for p in removed_items))
        if not_found:
            parts.append("Not approved: " + ", ".join(not_found))
        if invalid:
            parts.append("Invalid specs: " + ", ".join(invalid))
        return "\n\n".join(parts) if parts else "No users revoked."

    if action in {"block", "ban"}:
        if not args:
            return "Usage: /pa block platform:user_id [reason]"
        platform, user_id = _split_principal(args[0])
        if not platform or not user_id:
            return "Use platform:user_id, for example qqbot:OPENID."
        reason = " ".join(args[1:]).strip()
        principal = _principal(platform, user_id)
        _revoke_user(gateway, platform, user_id)
        state.setdefault("blocked", {})[principal] = {
            "reason": reason,
            "blocked_at": _now(),
            "blocked_by": admin,
        }
        for code, item in list(state.get("requests", {}).items()):
            if isinstance(item, dict) and item.get("principal") == principal:
                state["requests"].pop(code, None)
        _append_audit(state, "block", admin=admin, principal=principal, reason=reason)
        _save_state(state)
        return f"Blocked {principal}."

    if action in {"unblock", "unban"}:
        if not args:
            return "Usage: /pa unblock platform:user_id"
        platform, user_id = _split_principal(args[0])
        if not platform or not user_id:
            return "Use platform:user_id, for example qqbot:OPENID."
        principal = _principal(platform, user_id)
        existed = principal in state.get("blocked", {})
        state.get("blocked", {}).pop(principal, None)
        _append_audit(state, "unblock", admin=admin, principal=principal, existed=existed)
        _save_state(state)
        return f"Unblocked {principal}." if existed else f"{principal} was not blocked."

    _save_state(state)
    return _help()


def _handle_applicant(event: Any, gateway: Any) -> str:
    source = event.source
    platform = _platform_value(source.platform)
    user_id = str(source.user_id or "").strip()
    principal = _principal(platform, user_id)

    state = _load_state()
    _clean_expired_requests(state)

    if principal in state.get("blocked", {}):
        _save_state(state)
        return "blocked"

    created_request = False
    existing = _request_for_user(state, principal)
    if existing:
        code, item = existing
        item["last_seen_at"] = _now()
        state["requests"][code] = item
    else:
        created_request = True
        code = _new_code(state.get("requests", {}))
        item = {
            "code": code,
            "principal": principal,
            "platform": platform,
            "user_id": user_id,
            "user_name": getattr(source, "user_name", "") or "",
            "chat_id": getattr(source, "chat_id", "") or user_id,
            "chat_type": getattr(source, "chat_type", "") or "",
            "request_chat_id": getattr(source, "chat_id", "") or user_id,
            "first_text": str(getattr(event, "text", "") or "")[:500],
            "created_at": _now(),
            "last_seen_at": _now(),
        }
        state.setdefault("requests", {})[code] = item
        state.pop("last_pending_reminder_at", None)
        _append_audit(state, "request", principal=principal, code=code)

    _save_state(state)

    if created_request and _notify_admins_enabled():
        message = _format_request(code, item)
        for admin_platform, admin_chat_id in _admin_targets():
            _schedule_send(gateway, admin_platform, admin_chat_id, message)

    _schedule_send(
        gateway,
        platform,
        item.get("chat_id") or user_id,
        "Hermes access request sent. Please wait for admin approval.",
    )
    return "requested"


def _pre_gateway_dispatch(event: Any, gateway: Any, session_store: Any = None, **kwargs: Any) -> dict[str, str] | None:
    del session_store, kwargs
    _ensure_reminder_task(gateway)
    source = getattr(event, "source", None)
    if not _should_handle_source(event, gateway):
        return None

    platform = _platform_value(source.platform)
    user_id = str(getattr(source, "user_id", "") or "").strip()
    if not platform or not user_id:
        return None

    if _is_admin(source):
        if not _is_dm(source) and str(getattr(event, "text", "") or "").strip().startswith("/pa"):
            _schedule_send(
                gateway,
                platform,
                getattr(source, "chat_id", "") or user_id,
                "PA admin commands are only available in DM.",
            )
            return {"action": "skip", "reason": "pairing-admin-group-command-denied"}
        response = _handle_admin_command(event, gateway)
        if response is not None:
            _schedule_send(gateway, platform, _admin_reply_chat_id(source), response)
            return {"action": "skip", "reason": "pairing-admin-command"}
        return None

    if _is_approved(gateway, platform, user_id):
        return None

    outcome = _handle_applicant(event, gateway)
    return {"action": "skip", "reason": f"pairing-admin-{outcome}"}


def register(ctx: Any) -> None:
    ctx.register_hook("pre_gateway_dispatch", _pre_gateway_dispatch)
