import json
import os
import time

def load_dedications():
    """Dedikasyon verilerini yükler"""
    try:
        if os.path.exists('dedications.json'):
            if os.path.getsize('dedications.json') < 5:
                from backup_manager import restore_from_backup
                if restore_from_backup('dedications.json'):
                    print("Dedications restored from backup")
                    
            with open('dedications.json', 'r', encoding='utf-8') as f:
                return json.load(f)
        return {"current": None, "received": {}}
    except Exception as e:
        print(f"Dedikasyon verileri yüklenirken hata: {e}")
        from backup_manager import restore_from_backup
        if restore_from_backup('dedications.json'):
            try:
                with open('dedications.json', 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {"current": None, "received": {}}

def save_dedications(dedications):
    """Dedikasyon verilerini kaydeder"""
    from backup_manager import safe_json_save
    return safe_json_save('dedications.json', dedications)

def set_current_dedication(from_user, to_user, song_title):
    """Mevcut çalan şarkı için dedikasyon ayarlar"""
    dedications = load_dedications()
    
    # Şarkı hediyelerini kontrol et
    current_song_gifts = dedications.get("current_song_gifts", {})
    
    # Eğer bu şarkı daha önce aynı kişiye hediye edilmiş mi kontrol et
    if song_title in current_song_gifts:
        previous_gifts = current_song_gifts[song_title]
        for gift in previous_gifts:
            if gift["to"] == to_user:
                return {"status": False, "previous_from": gift["from"], "previous_to": gift["to"]}

    # Mevcut şarkı için hediye bilgisini kaydet
    if "current_song_gifts" not in dedications:
        dedications["current_song_gifts"] = {}
    
    if song_title not in dedications["current_song_gifts"]:
        dedications["current_song_gifts"][song_title] = []
    
    dedications["current_song_gifts"][song_title].append({
        "from": from_user,
        "to": to_user,
        "time": time.time()
    })

    # Alıcının alınan dedikasyonlar listesine ekle
    if to_user not in dedications["received"]:
        dedications["received"][to_user] = []

    dedications["received"][to_user].append({
        "from": from_user,
        "song": song_title,
        "time": time.time()
    })

    save_dedications(dedications)
    return {"status": True}

def get_user_dedications(username):
    """Kullanıcının aldığı dedikasyonları döndürür"""
    dedications = load_dedications()
    
    # Eğer "received" anahtarı yoksa boş dict olarak oluştur
    if "received" not in dedications:
        dedications["received"] = {}
        save_dedications(dedications)
    
    if username in dedications["received"]:
        # Zamana göre sırala (en yeniden en eskiye)
        sorted_dedications = sorted(
            dedications["received"][username], 
            key=lambda x: x["time"], 
            reverse=True
        )
        
        # Tarih bilgisini çıkartarak sadece from ve song bilgilerini döndür
        result = []
        for dedication in sorted_dedications:
            result.append({
                "from": dedication["from"],
                "song": dedication["song"]
            })
        return result
    return []

def get_current_dedication():
    """Mevcut dedikasyonu döndürür"""
    dedications = load_dedications()
    return dedications.get("current")

def clear_current_dedication():
    """Mevcut şarkı için olan hediye bilgilerini temizler"""
    dedications = load_dedications()
    dedications["current_song_gifts"] = {}
    return save_dedications(dedications)