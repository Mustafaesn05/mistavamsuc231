import json
import os
import threading
import time

# Thread safety için lock
_wallet_lock = threading.Lock()

def save_wallets(wallets):
    from backup_manager import safe_json_save
    return safe_json_save('wallets.json', wallets)

def load_wallets():
    try:
        if os.path.exists('wallets.json'):
            if os.path.getsize('wallets.json') < 5:
                from backup_manager import restore_from_backup
                if restore_from_backup('wallets.json'):
                    print("Wallets restored from backup")
                    
            with open('wallets.json', 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    except Exception as e:
        print(f"Error loading wallets: {e}")
        from backup_manager import restore_from_backup
        if restore_from_backup('wallets.json'):
            try:
                with open('wallets.json', 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {}

def add_gold(username, amount):
    max_retries = 3
    retry_count = 0

    while retry_count < max_retries:
        try:
            with _wallet_lock:
                wallets = load_wallets()
                if username not in wallets:
                    wallets[username] = {"gold": 0}

                wallets[username]["gold"] += amount
                if save_wallets(wallets):
                    return True
                else:
                    retry_count += 1
                    time.sleep(0.1)
        except Exception as e:
            print(f"Error adding gold for {username} (attempt {retry_count + 1}): {e}")
            retry_count += 1
            time.sleep(0.1)

    print(f"Failed to add gold for {username} after {max_retries} attempts")
    return False

def add_gold_without_wager(username, amount):
    max_retries = 3
    retry_count = 0

    while retry_count < max_retries:
        try:
            with _wallet_lock:
                wallets = load_wallets()
                if username not in wallets:
                    wallets[username] = {
                        "gold": 0,
                        "required_wager": 0,
                        "last_update": time.time()
                    }
                wallets[username]["gold"] += amount
                wallets[username]["last_update"] = time.time()
                if save_wallets(wallets):
                    return True
                else:
                    retry_count += 1
                    time.sleep(0.1)
        except Exception as e:
            print(f"Error adding gold for {username} (attempt {retry_count + 1}): {e}")
            retry_count += 1
            time.sleep(0.1)

    print(f"Failed to add gold without wager for {username} after {max_retries} attempts")
    return False

def add_wagered(username, amount):
    max_retries = 3
    retry_count = 0

    while retry_count < max_retries:
        try:
            with _wallet_lock:
                wallets = load_wallets()
                if username not in wallets:
                    wallets[username] = {
                        "gold": 0,
                        "required_wager": 0,
                        "last_update": time.time()
                    }
                current_required = wallets[username].get("required_wager", 0)
                if current_required > 0:
                    # Double olduğunda amount'un 2 katını çıkar
                    wallets[username]["required_wager"] = max(0, current_required - (amount * 2))
                if save_wallets(wallets):
                    return True
                else:
                    retry_count += 1
                    time.sleep(0.1)
        except Exception as e:
            print(f"Error adding wagered amount for {username} (attempt {retry_count + 1}): {e}")
            retry_count += 1
            time.sleep(0.1)

    print(f"Failed to add wagered amount for {username} after {max_retries} attempts")
    return False

def get_wagered(username):
    try:
        with _wallet_lock:
            wallets = load_wallets()
            return wallets.get(username, {}).get("required_wager", 0)
    except Exception as e:
        print(f"Error getting wagered amount for {username}: {e}")
        return 0

def get_gold(username):
    try:
        with _wallet_lock:
            wallets = load_wallets()
            return wallets.get(username, {}).get("gold", 0)
    except Exception as e:
        print(f"Error getting gold for {username}: {e}")
        return 0

def use_gold(username, amount):
    max_retries = 3
    retry_count = 0

    while retry_count < max_retries:
        try:
            with _wallet_lock:
                wallets = load_wallets()
                if username not in wallets:
                    return False

                if wallets[username]["gold"] >= amount:
                    wallets[username]["gold"] -= amount
                    wallets[username]["last_update"] = time.time() #Keep the update time
                    if save_wallets(wallets):
                        return True
                    else:
                        retry_count += 1
                        time.sleep(0.1)
                else:
                    return False
        except Exception as e:
            print(f"Error using gold for {username} (attempt {retry_count + 1}): {e}")
            retry_count += 1
            time.sleep(0.1)

    print(f"Failed to use gold for {username} after {max_retries} attempts")
    return False