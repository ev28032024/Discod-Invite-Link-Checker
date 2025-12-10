import requests
import json
import random
import concurrent.futures

class config():
    with open("config.json", "r") as cfg:
        data = json.load(cfg)
        min_members = data[0]["min_members"]
        max_members = data[0]["max_members"]
        min_members_online = data[0]["min_members_online"]
        min_boosts = data[0]["min_boosts"]
        use_proxies = data[0]["use_proxies"]
        threads = data[0]["threads"]
        save_only_permanent_invites = data[0]["save_only_permanent_invites"]

class counter():
    hit = 0
    bad = 0
    failed = 0

deduped_proxies = []

def send_request(invite_code):
    if config.use_proxies == True:
        
        global deduped_proxies
        proxy = random.choice(deduped_proxies)

        try:
            # print(f"DEBUG > Using proxy: {proxy}")
            r = requests.get(url=f"https://discordapp.com/api/v6/invites/{invite_code}?with_counts=true&?with_expiration=true", timeout=7.5, proxies={"http": f"http://{proxy}", "https": f"https://{proxy}"})
            return r.json()
        
        except Exception as e:
            print(f"[FAILED] - Failed Request: {invite_code} - {e}")
            with open("failed.txt", "a") as failed_file:
                failed_file.write(f"{invite_code}\n")
            counter.failed += 1
            return None

    else:
        try:
            r = requests.get(url=f"https://discordapp.com/api/v6/invites/{invite_code}?with_counts=true&?with_expiration=true", timeout=5) # no proxy
            return r.json()
        
        except Exception as e:
            print(f"[FAILED] - Failed Request: {invite_code} - {e}")
            with open("failed.txt", "a") as failed_file:
                failed_file.write(f"{invite_code}\n")
            counter.failed += 1
            return None

def check_invite(invite_code):

    response_data = send_request(invite_code=invite_code)
    if response_data != None:

        try:

            invite_type = response_data["type"] # Should be 0, otherwhise its not a server invite
            expires_at = response_data["expires_at"] # if == "null" it never expires, otherwhise shows a date
            guild_id = response_data["guild"]["id"] # Server ID. Can be used later to counter dupes
            guild_name = response_data["guild"]["name"] # Name of the guild. Only used to show in displayed log
            boosts = response_data["guild"]["premium_subscription_count"] # Count boosts amount
            members = response_data["approximate_member_count"] # Member count
            members_online = response_data["approximate_presence_count"] # Members online count

            # print(f"""Debug test:\nCode: {invite_code}\nInvite Type: {invite_type}\nExpires At: {expires_at}\nGuild ID: {guild_id}\nGuild Name: {guild_name}\nBoosts: {boosts}\nMembers: {members}\nMembers Online: {members_online}\n\nWohoo!""")

            guilds_ids = []

            if guild_id in guilds_ids: # Guild was already checked before
                print("Duped guild!")
                pass
            else: 
                if invite_type == 0:
                    guilds_ids.append(guild_id)
                    if members >= config.min_members and members <= config.max_members:
                        if boosts >= config.min_boosts:
                            if members_online >= config.min_members_online:
                                if config.save_only_permanent_invites == True:
                                    if expires_at == None:
                                        print(f"[HIT] - Valid Invite: {invite_code} · Members: {members_online}/{members} · Boosts: {boosts} · Guild: {guild_name} ({guild_id})")
                                        with open("valid.txt", "a") as validfile:
                                            validfile.write(f"{invite_code}\n")
                                        with open("valid_ids.txt", "a") as valid_ids_file:
                                            valid_ids_file.write(f"{guild_id}\n")
                                        counter.hit += 1
                                    else:
                                        print(f"[BAD] - Invite Not Permanent: {invite_code}")
                                        with open("bad.txt", "a") as bad_file:
                                            bad_file.write(f"{invite_code}\n")
                                        counter.bad += 1
                                else:
                                    print(f"[HIT] - Valid Invite: {invite_code} · Members: {members_online}/{members} · Boosts: {boosts} · Guild: {guild_name} ({guild_id})")
                                    with open("valid.txt", "a") as validfile:
                                        validfile.write(f"{invite_code}\n")
                                    with open("valid_ids.txt", "a") as valid_ids_file:
                                        valid_ids_file.write(f"{guild_id}")
                                    counter.hit += 1
                            else:
                                print(f"[BAD] - Not Enough Members Online: {invite_code}")
                                with open("bad.txt", "a") as bad_file:
                                    bad_file.write(f"{invite_code}\n")
                                counter.bad += 1
                        else:
                            print(f"[BAD] - Not Enough Boosts: {invite_code}")
                            with open("bad.txt", "a") as bad_file:
                                bad_file.write(f"{invite_code}\n")
                            counter.bad += 1
                    else:
                        print(f"[BAD] - Member Amount Mismatch: {invite_code}")
                        with open("bad.txt", "a") as bad_file:
                            bad_file.write(f"{invite_code}\n")
                        counter.bad += 1
                else:
                    print(f"[BAD] - Not a Server Invite: {invite_code}")
                    with open("bad.txt", "a") as bad_file:
                        bad_file.write(f"{invite_code}\n")
                    counter.bad += 1


        except KeyError:
            print(f"[BAD] - Dead Invite: {invite_code}")
            with open("invalid.txt", "a") as invalid_file:
                invalid_file.write(f"{invite_code}\n")
            counter.bad += 1

        except Exception as e:
            print(f"[FAILED] - Failed Checking: {invite_code} - {e}")
            with open("failed.txt", "a") as failed_file:
                failed_file.write(f"{invite_code}\n")
            counter.failed += 1

    else:
        pass

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

    input(f"Please put your invite CODES (not invite links) into invites.txt. An invite link looks like this: https://discord.gg/example123 , It's code is \"example123\".\n\nPress ENTER to launch the checker.")       

    with open("proxies.txt", "r", encoding="utf-8", errors="ignore") as proxies_file:
            proxies = proxies_file.readlines()
            print(f"Successfully loaded {sum(1 for proxie in proxies)} proxies from proxies.txt!")
            global deduped_proxies
            p_dupes_count = 0
            for proxie in proxies:
                proxie = proxie.strip()
                if proxie not in deduped_proxies:
                    deduped_proxies.append(proxie)
                else:
                    p_dupes_count =+ 1
            print(f"Ignoring {p_dupes_count} duplicate proxies...")

    with open("invites.txt", "r", encoding="utf-8", errors="ignore") as invites_file:
        invites = invites_file.readlines()
        print(f"Successfully loaded {sum(1 for invite in invites)} invites from invites.txt!")
        deduped_invites = []
        dupes_count = 0
        for invite in invites:
            invite = invite.strip()
            if invite not in deduped_invites:
                deduped_invites.append(invite)
            else:
                dupes_count =+ 1
        print(f"Ignoring {dupes_count} duplicate invites...")

        #for deduped_invite in deduped_invites:
            #check_invite(deduped_invite)
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=config.threads) as executor:
            executor.map(check_invite, deduped_invites)

        print(f"Checking Process Finished. Results: \nHits: {counter.hit}, Bad: {counter.bad}, Failed: {counter.failed}")   

main()