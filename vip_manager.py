
import json
import os

def save_vips(vip_data):
    from backup_manager import safe_json_save
    return safe_json_save('vips.json', vip_data)

def load_vips():
    try:
        if os.path.exists('vips.json'):
            if os.path.getsize('vips.json') < 5:
                from backup_manager import restore_from_backup
                if restore_from_backup('vips.json'):
                    print("VIPs restored from backup")
                    
            with open('vips.json', 'r', encoding='utf-8') as f:
                vips = json.load(f)
                # Eski format kontrolü - eğer liste ise yeni formata çevir
                if isinstance(vips, list):
                    # Eski VIP'leri Kademe 1 olarak kaydet
                    new_vips = {
                        "level_1": vips,
                        "level_2": [],
                        "level_3": []
                    }
                    save_vips(new_vips)
                    return new_vips
                return vips if isinstance(vips, dict) else {"level_1": [], "level_2": [], "level_3": []}
        return {"level_1": [], "level_2": [], "level_3": []}
    except Exception as e:
        print(f"Error loading vips: {e}")
        from backup_manager import restore_from_backup
        if restore_from_backup('vips.json'):
            try:
                with open('vips.json', 'r', encoding='utf-8') as f:
                    vips = json.load(f)
                    if isinstance(vips, list):
                        new_vips = {
                            "level_1": vips,
                            "level_2": [],
                            "level_3": []
                        }
                        return new_vips
                    return vips if isinstance(vips, dict) else {"level_1": [], "level_2": [], "level_3": []}
            except:
                pass
        return {"level_1": [], "level_2": [], "level_3": []}

def get_user_vip_level(username):
    """Kullanıcının VIP seviyesini döndürür. VIP değilse 0 döner."""
    vips = load_vips()
    
    if username in vips.get("level_3", []):
        return 3
    elif username in vips.get("level_2", []):
        return 2
    elif username in vips.get("level_1", []):
        return 1
    else:
        return 0

def add_vip(username, level):
    """Kullanıcıyı belirtilen seviyeye VIP olarak ekler"""
    if level not in [1, 2, 3]:
        return False
    
    vips = load_vips()
    level_key = f"level_{level}"
    
    # Önce diğer seviyelerden kaldır
    for other_level in [1, 2, 3]:
        other_key = f"level_{other_level}"
        if username in vips.get(other_key, []):
            vips[other_key].remove(username)
    
    # Yeni seviyeye ekle
    if username not in vips.get(level_key, []):
        vips[level_key].append(username)
        return save_vips(vips)
    
    return True

def remove_vip(username):
    """Kullanıcıyı tüm VIP seviyelerinden kaldırır"""
    vips = load_vips()
    removed = False
    
    for level in [1, 2, 3]:
        level_key = f"level_{level}"
        if username in vips.get(level_key, []):
            vips[level_key].remove(username)
            removed = True
    
    if removed:
        return save_vips(vips)
    return False

def get_vip_emoji(level):
    """VIP seviyesine göre emoji döndürür"""
    emojis = {
        1: "⭐",
        2: "🌟", 
        3: "💎"
    }
    return emojis.get(level, "")

def get_max_songs_for_user(username, is_admin=False):
    """Kullanıcının maksimum şarkı ekleme sayısını döndürür"""
    if is_admin:
        return float('inf')
    
    vip_level = get_user_vip_level(username)
    if vip_level >= 1:
        return 2  # Tüm VIP seviyeleri 2 şarkı
    else:
        return 1  # Normal kullanıcılar 1 şarkı
