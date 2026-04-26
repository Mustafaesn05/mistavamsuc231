
import json
import os
import time

def save_telafi_used(telafi_data):
    from backup_manager import safe_json_save
    return safe_json_save('telafi_used.json', telafi_data)

def load_telafi_used():
    try:
        if os.path.exists('telafi_used.json'):
            if os.path.getsize('telafi_used.json') < 5:
                from backup_manager import restore_from_backup
                if restore_from_backup('telafi_used.json'):
                    print("Telafi data restored from backup")
                    
            with open('telafi_used.json', 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    except Exception as e:
        print(f"Error loading telafi data: {e}")
        from backup_manager import restore_from_backup
        if restore_from_backup('telafi_used.json'):
            try:
                with open('telafi_used.json', 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {}

def has_user_used_telafi(username):
    """Kullanıcının telafi komutunu kullanıp kullanmadığını kontrol eder"""
    telafi_data = load_telafi_used()
    return username in telafi_data

def use_telafi_command(username):
    """Kullanıcının telafi komutunu kullandığını kaydeder"""
    telafi_data = load_telafi_used()
    telafi_data[username] = {
        "used": True,
        "timestamp": time.time()
    }
    return save_telafi_used(telafi_data)
