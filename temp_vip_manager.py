
import json
import os
import time
from datetime import datetime, timedelta

def load_temp_vips():
    try:
        if os.path.exists('temp_vips.json'):
            with open('temp_vips.json', 'r', encoding='utf-8') as f:
                temp_vips = json.load(f)
                return temp_vips
        return {"temp_vips": []}
    except Exception as e:
        print(f"Error loading temp vips: {e}")
        return {"temp_vips": []}

def save_temp_vips(temp_vips_data):
    try:
        with open('temp_vips.json', 'w', encoding='utf-8') as f:
            json.dump(temp_vips_data, f, ensure_ascii=False, indent=4)
            f.flush()
            os.fsync(f.fileno())
        return True
    except Exception as e:
        print(f"Error saving temp vips: {e}")
        return False

def add_temp_vip(username, level, duration_days=30):
    """Geçici VIP ekler"""
    temp_vips = load_temp_vips()
    
    # Önce mevcut geçici VIP'i kaldır
    temp_vips["temp_vips"] = [vip for vip in temp_vips["temp_vips"] if vip["username"] != username]
    
    # Yeni geçici VIP ekle
    expiry_date = datetime.now() + timedelta(days=duration_days)
    new_temp_vip = {
        "username": username,
        "level": level,
        "start_date": datetime.now().isoformat(),
        "expiry_date": expiry_date.isoformat()
    }
    
    temp_vips["temp_vips"].append(new_temp_vip)
    
    # Kalıcı VIP listesine de ekle
    from vip_manager import add_vip
    add_vip(username, level)
    
    return save_temp_vips(temp_vips)

def check_expired_vips():
    """Süresi dolmuş VIP'leri kontrol eder ve kaldırır"""
    temp_vips = load_temp_vips()
    current_time = datetime.now()
    
    expired_users = []
    active_vips = []
    
    for temp_vip in temp_vips["temp_vips"]:
        expiry_date = datetime.fromisoformat(temp_vip["expiry_date"])
        if current_time >= expiry_date:
            expired_users.append(temp_vip["username"])
        else:
            active_vips.append(temp_vip)
    
    # Süresi dolanları kaldır
    if expired_users:
        from vip_manager import remove_vip
        for username in expired_users:
            remove_vip(username)
    
    # Aktif VIP'leri kaydet
    temp_vips["temp_vips"] = active_vips
    save_temp_vips(temp_vips)
    
    return expired_users

def get_temp_vip_info(username):
    """Kullanıcının geçici VIP bilgilerini döndürür"""
    temp_vips = load_temp_vips()
    
    for temp_vip in temp_vips["temp_vips"]:
        if temp_vip["username"] == username:
            expiry_date = datetime.fromisoformat(temp_vip["expiry_date"])
            days_left = (expiry_date - datetime.now()).days
            return {
                "level": temp_vip["level"],
                "days_left": max(0, days_left),
                "expiry_date": expiry_date.strftime("%Y-%m-%d")
            }
    
    return None
