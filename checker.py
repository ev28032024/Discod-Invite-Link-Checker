import concurrent.futures
import json
import random
import re
from dataclasses import dataclass
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

    @classmethod
    def load(cls) -> "Config":
        with open("config.json", "r", encoding="utf-8") as cfg:
            data = json.load(cfg)[0]
        return cls(
            min_members=data["min_members"],
            max_members=data["max_members"],
            min_members_online=data["min_members_online"],
            min_boosts=data["min_boosts"],
            use_proxies=data["use_proxies"],
            threads=data["threads"],
            save_only_permanent_invites=data["save_only_permanent_invites"],
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


def main():
    title = """
 ██▓ ███▄    █ ██▒   █▓ ██▓▄▄▄█████▓▓█████     ▄████▄   ██░ ██ ▓█████  ▄████▄   ██ ▄█▀▓█████  ██▀███
▓██▒ ██ ▀█   █▓██░   █▒▓██▒▓  ██▒ ▓▒▓█   ▀    ▒██▀ ▀█  ▓██░ ██▒▓█   ▀ ▒██▀ ▀█   ██▄█▒ ▓█   ▀ ▓██ ▒ ██▒
▒██▒▓██  ▀█ ██▒▓██  █▒░▒██▒▒ ▓██░ ▒░▒███      ▒▓█    ▄ ▒██▀▀██░▒███   ▒▓█    ▄ ▓███▄░ ▒███   ▓██ ░▄█ ▒
░██░▓██▒  ▐▌██▒ ▒██ █░░░██░░ ▓██▓ ░ ▒▓█  ▄    ▒▓▓▄ ▄██▒░▓█ ░██ ▒▓█  ▄ ▒▓▓▄ ▄██▒▓██ █▄ ▒▓█  ▄ ▒██▀▀█▄
░██░▒██░   ▓██░  ▒▀█░  ░██░  ▒██▒ ░ ░▒████▒   ▒ ▓███▀ ░░▓█▒░██▓░▒████▒▒ ▓███▀ ░▒██▒ █▄░▒████▒░██▓ ▒██▒
░▓  ░ ▒░   ▒ ▒   ░ ▐░  ░▓    ▒ ░░   ░░ ▒░ ░   ░ ░▒ ▒  ░ ▒ ░░▒░▒░░ ▒░ ░░ ░▒ ▒  ░▒ ▒▒ ▓▒░░ ▒░ ░░ ▒▓ ░▒▓░
 ▒ ░░ ░░   ░ ▒░  ░ ░░   ▒ ░    ░     ░ ░  ░     ░  ▒    ▒ ░▒░ ░ ░ ░  ░  ░  ▒   ░ ░▒ ▒░ ░ ░  ░  ░▒ ░ ▒░
 ▒ ░   ░   ░ ░     ░░   ▒ ░  ░         ░      ░         ░  ░░ ░   ░   ░        ░ ░░ ░    ░     ░░   ░
 ░           ░      ░   ░              ░  ░   ░ ░       ░  ░  ░   ░  ░░ ░      ░  ░      ░  ░   ░
                   ░                          ░                       ░


                   -> Coded by @tec9_xd#0 / @tec9_eu

                                                        Version: Release 1.0




                                                        """

    print(title)

    input(
        "Please put your invite CODES or LINKS into invites.txt. "
        "Links such as https://discord.gg/example123 or https://discord.com/invite/example123 "
        "will be automatically parsed.\n\nPress ENTER to launch the checker."
    )

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

    with open("invites.txt", "r", encoding="utf-8", errors="ignore") as invites_file:
        invites = invites_file.readlines()
        print(f"Successfully loaded {sum(1 for invite in invites)} invites from invites.txt!")
        deduped_invites = []
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

        with concurrent.futures.ThreadPoolExecutor(max_workers=config.threads) as executor:
            executor.map(check_invite, deduped_invites)

        print(f"Checking Process Finished. Results: \nHits: {counter.hit}, Bad: {counter.bad}, Failed: {counter.failed}")


if __name__ == "__main__":
    main()
