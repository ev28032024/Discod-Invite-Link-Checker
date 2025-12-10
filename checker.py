import concurrent.futures
import json
import random
import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import requests


@dataclass
class Config:
    min_members: int
    max_members: int
    min_members_online: int
    min_boosts: int
    use_proxies: bool
    threads: int
    save_only_permanent_invites: bool
    auto_mode: bool
    check_interval_minutes: float
    telegram_bot_token: Optional[str]
    telegram_chat_id: Optional[int]
    telegram_thread_id: Optional[int]
    telegram_mentions: list[str]

    @classmethod
    def load(cls) -> "Config":
        with open("config.json", "r", encoding="utf-8") as cfg:
            data = json.load(cfg)[0]
        return cls(
            min_members=data.get("min_members", 0),
            max_members=data.get("max_members", 0),
            min_members_online=data.get("min_members_online", 0),
            min_boosts=data.get("min_boosts", 0),
            use_proxies=data.get("use_proxies", False),
            threads=data.get("threads", 1),
            save_only_permanent_invites=data.get("save_only_permanent_invites", False),
            auto_mode=data.get("auto_mode", False),
            check_interval_minutes=data.get("check_interval_minutes", 60),
            telegram_bot_token=data.get("telegram_bot_token"),
            telegram_chat_id=data.get("telegram_chat_id"),
            telegram_thread_id=data.get("telegram_thread_id"),
            telegram_mentions=data.get("telegram_mentions", []),
        )


@dataclass
class Counter:
    hit: int = 0
    bad: int = 0
    failed: int = 0


config = Config.load()
counter = Counter()
deduped_proxies: list[str] = []
checked_guild_ids: set[str] = set()


def normalize_invite(invite: str) -> Optional[str]:
    """Extract the invite code from common Discord invite formats."""

    invite = invite.strip()
    if not invite:
        return None

    match = re.search(
        r"(?:https?://)?(?:www\.)?(?:discord(?:app)?\.com/invite/|disco?d\.gg/)?([A-Za-z0-9-]+)(?:/)?$",
        invite,
    )
    if match:
        return match.group(1)

    return None


def send_request(invite_code: str) -> Optional[dict]:
    url = f"https://discord.com/api/v9/invites/{invite_code}?with_counts=true&with_expiration=true"
    request_kwargs = {"timeout": 7.5}

    if config.use_proxies and deduped_proxies:
        proxy = random.choice(deduped_proxies)
        request_kwargs["proxies"] = {"http": f"http://{proxy}", "https": f"https://{proxy}"}

    try:
        response = requests.get(url=url, **request_kwargs)
        if response.status_code != 200:
            raise ValueError(f"Unexpected status code {response.status_code}")
        return response.json()
    except Exception as exc:  # noqa: BLE001 - broad to log failure reasons for end users
        print(f"[FAILED] - Failed Request: {invite_code} - {exc}")
        with open("failed.txt", "a", encoding="utf-8") as failed_file:
            failed_file.write(f"{invite_code}\n")
        counter.failed += 1
        return None


def reset_state():
    counter.hit = 0
    counter.bad = 0
    counter.failed = 0
    checked_guild_ids.clear()
    deduped_proxies.clear()


def load_proxies():
    with open("proxies.txt", "r", encoding="utf-8", errors="ignore") as proxies_file:
        proxies = proxies_file.readlines()
        print(f"Successfully loaded {sum(1 for proxie in proxies)} proxies from proxies.txt!")
        p_dupes_count = 0
        for proxie in proxies:
            proxie = proxie.strip()
            if proxie and proxie not in deduped_proxies:
                deduped_proxies.append(proxie)
            elif proxie:
                p_dupes_count += 1
        print(f"Ignoring {p_dupes_count} duplicate proxies...")


def load_invites() -> list[str]:
    with open("invites.txt", "r", encoding="utf-8", errors="ignore") as invites_file:
        invites = invites_file.readlines()
        print(f"Successfully loaded {sum(1 for invite in invites)} invites from invites.txt!")
        deduped_invites: list[str] = []
        dupes_count = 0
        for invite in invites:
            invite_code = normalize_invite(invite)
            if not invite_code:
                continue
            if invite_code not in deduped_invites:
                deduped_invites.append(invite_code)
            else:
                dupes_count += 1
        print(f"Ignoring {dupes_count} duplicate invites...")
        return deduped_invites


def handle_result(
    invite_code: str,
    guild_id: str,
    guild_name: str,
    members_online: int,
    members: int,
    boosts: int,
    expires_at,
):
    is_permanent = expires_at is None
    meets_member_bounds = config.min_members <= members <= config.max_members
    if not meets_member_bounds:
        print(
            f"[BAD] - Member Amount Mismatch: {invite_code} · "
            f"Got {members} members; expected between {config.min_members} and {config.max_members}"
        )
        with open("bad.txt", "a", encoding="utf-8") as bad_file:
            bad_file.write(f"{invite_code}\n")
        counter.bad += 1
        return

    if boosts < config.min_boosts:
        print(
            f"[BAD] - Not Enough Boosts: {invite_code} · "
            f"Got {boosts} boosts; expected at least {config.min_boosts}"
        )
        with open("bad.txt", "a", encoding="utf-8") as bad_file:
            bad_file.write(f"{invite_code}\n")
        counter.bad += 1
        return

    if members_online < config.min_members_online:
        print(
            f"[BAD] - Not Enough Members Online: {invite_code} · "
            f"Got {members_online} online; expected at least {config.min_members_online}"
        )
        with open("bad.txt", "a", encoding="utf-8") as bad_file:
            bad_file.write(f"{invite_code}\n")
        counter.bad += 1
        return

    if config.save_only_permanent_invites and not is_permanent:
        print(f"[BAD] - Invite Not Permanent: {invite_code}")
        with open("bad.txt", "a", encoding="utf-8") as bad_file:
            bad_file.write(f"{invite_code}\n")
        counter.bad += 1
        return

    print(
        f"[HIT] - Valid Invite: {invite_code} · Members: {members_online}/{members} · "
        f"Boosts: {boosts} · Guild: {guild_name} ({guild_id})"
    )
    with open("valid.txt", "a", encoding="utf-8") as valid_file:
        valid_file.write(f"{invite_code}\n")
    with open("valid_ids.txt", "a", encoding="utf-8") as valid_ids_file:
        valid_ids_file.write(f"{guild_id}\n")
    counter.hit += 1
    send_telegram_notification(
        invite_code=invite_code,
        guild_name=guild_name,
        members_online=members_online,
        members=members,
        boosts=boosts,
        is_permanent=is_permanent,
    )


def send_telegram_notification(
    invite_code: str,
    guild_name: str,
    members_online: int,
    members: int,
    boosts: int,
    is_permanent: bool,
    ):
    if not config.telegram_bot_token or not config.telegram_chat_id:
        return

    mentions = " ".join(
        f"@{username.lstrip('@')}" for username in config.telegram_mentions if username.strip()
    )
    invite_link = f"https://discord.gg/{invite_code}"
    project_name = guild_name
    permanent_text = "Да" if is_permanent else "Нет"

    message_body = (
        f"<b>🎉 Найдено рабочее приглашение</b>\n"
        f"<b>Проект:</b> {project_name}\n"
        f"<b>Сервер:</b> {guild_name}\n"
        f"<b>Ссылка:</b> <a href=\"{invite_link}\">{invite_link}</a>\n"
        f"<b>Онлайн:</b> {members_online}/{members}\n"
        f"<b>Бусты:</b> {boosts}\n"
        f"<b>Постоянное приглашение:</b> {permanent_text}"
    )

    payload = {
        "chat_id": config.telegram_chat_id,
        "text": f"{mentions}\n{message_body}".strip(),
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    if config.telegram_thread_id:
        payload["message_thread_id"] = config.telegram_thread_id

    try:
        response = requests.post(
            url=f"https://api.telegram.org/bot{config.telegram_bot_token}/sendMessage",
            json=payload,
            timeout=10,
        )
        response.raise_for_status()
    except Exception as exc:  # noqa: BLE001 - broad to log failure reasons for end users
        print(f"[FAILED] - Telegram notification not sent: {exc}")


def check_invite(invite_code: str):
    response_data = send_request(invite_code=invite_code)
    if response_data is None:
        return

    try:
        invite_type = response_data["type"]
        expires_at = response_data.get("expires_at")
        guild = response_data["guild"]
        guild_id = guild["id"]
        guild_name = guild["name"]
        boosts = guild.get("premium_subscription_count", 0)
        members = response_data.get("approximate_member_count", 0)
        members_online = response_data.get("approximate_presence_count", 0)

        if guild_id in checked_guild_ids:
            print(f"[INFO] - Duplicate Guild Skipped: {invite_code}")
            return

        if invite_type != 0:
            print(f"[BAD] - Not a Server Invite: {invite_code}")
            with open("bad.txt", "a", encoding="utf-8") as bad_file:
                bad_file.write(f"{invite_code}\n")
            counter.bad += 1
            return

        checked_guild_ids.add(guild_id)
        handle_result(invite_code, guild_id, guild_name, members_online, members, boosts, expires_at)
    except KeyError:
        print(f"[BAD] - Dead Invite: {invite_code}")
        with open("invalid.txt", "a", encoding="utf-8") as invalid_file:
            invalid_file.write(f"{invite_code}\n")
        counter.bad += 1
    except Exception as exc:  # noqa: BLE001 - broad to log failure reasons for end users
        print(f"[FAILED] - Failed Checking: {invite_code} - {exc}")
        with open("failed.txt", "a", encoding="utf-8") as failed_file:
            failed_file.write(f"{invite_code}\n")
        counter.failed += 1


def run_checker_once():
    reset_state()
    load_proxies()
    deduped_invites = load_invites()

    with concurrent.futures.ThreadPoolExecutor(max_workers=config.threads) as executor:
        executor.map(check_invite, deduped_invites)

    print(
        f"Checking Process Finished. Results: \nHits: {counter.hit}, Bad: {counter.bad}, Failed: {counter.failed}"
    )


def main():
    if not config.auto_mode:
        input(
            "Please put your invite CODES or LINKS into invites.txt. "
            "Links such as https://discord.gg/example123 or https://discord.com/invite/example123 "
            "will be automatically parsed.\n\nPress ENTER to launch the checker."
        )
        run_checker_once()
        return

    print(
        "Automatic mode enabled. The checker will run continuously. Press CTRL+C to stop the process.\n"
        f"Current interval: every {config.check_interval_minutes} minute(s)."
    )

    try:
        while True:
            print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starting invite check cycle...")
            run_checker_once()
            sleep_seconds = max(config.check_interval_minutes * 60, 1)
            print(
                f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Waiting {config.check_interval_minutes} minute(s) before the next run..."
            )
            time.sleep(sleep_seconds)
    except KeyboardInterrupt:
        print("\n[INFO] - Automatic checking stopped by user.")


if __name__ == "__main__":
    main()
