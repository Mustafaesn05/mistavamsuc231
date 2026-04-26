
import json
import time
import os

# Her kullanıcının son kullandığı komutları ve zamanları takip etmek için
def load_cooldowns():
    try:
        if os.path.exists('command_cooldowns.json'):
            with open('command_cooldowns.json', 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    except Exception as e:
        print(f"Error loading cooldowns: {e}")
        return {}

def save_cooldowns(cooldowns):
    try:
        with open('command_cooldowns.json', 'w', encoding='utf-8') as f:
            json.dump(cooldowns, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"Error saving cooldowns: {e}")

# Kullanıcının komutu kullanabilir durumda olup olmadığını kontrol et
def check_command_cooldown(username, command, cooldown_seconds=3):
    # Admin kullanıcılar için cooldown yok
    from admin_manager import load_admins
    admins = load_admins()
    if username in admins:
        return True, 0
    
    cooldowns = load_cooldowns()
    current_time = time.time()
    
    # Kullanıcının kayıtlı komutlarını kontrol et
    if username not in cooldowns:
        cooldowns[username] = {}
    
    user_cooldowns = cooldowns[username]
    
    if command in user_cooldowns:
        last_used = user_cooldowns[command]
        time_diff = current_time - last_used
        
        if time_diff < cooldown_seconds:
            # Komut bekleme süresinde, kalan süreyi hesapla
            remaining = cooldown_seconds - time_diff
            return False, remaining
    
    # Komut kullanılabilir, son kullanım zamanını güncelle
    user_cooldowns[command] = current_time
    cooldowns[username] = user_cooldowns
    save_cooldowns(cooldowns)
    
    return True, 0
