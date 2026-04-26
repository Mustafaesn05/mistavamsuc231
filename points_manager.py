import json
import os
import time
import threading
from datetime import datetime, timedelta
from blacklist_manager import load_blacklist

# Thread safety için lock
_points_lock = threading.Lock()

def load_points():
    try:
        if os.path.exists('user_points.json'):
            # Dosya boyutunu kontrol et
            if os.path.getsize('user_points.json') < 5:  # Çok küçükse backup'tan yükle
                print("Main points file corrupted, trying backup...")
                from backup_manager import restore_from_backup
                if restore_from_backup('user_points.json'):
                    print("Restored from backup")
                else:
                    print("No valid backup found, starting fresh")
                    return {}

            with open('user_points.json', 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Veri doğrulaması
                if not isinstance(data, dict):
                    print("Invalid data format, starting fresh")
                    return {}
                return data
        return {}
    except (json.JSONDecodeError, Exception) as e:
        print(f"Error loading points: {e}")
        # Backup'tan yüklemeyi dene
        from backup_manager import restore_from_backup
        if restore_from_backup('user_points.json'):
            try:
                with open('user_points.json', 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        print("Loaded from backup due to main file corruption")
                        return data
            except Exception as backup_error:
                print(f"Backup loading failed: {backup_error}")

        return {}

def save_points(points_data):
    from backup_manager import safe_json_save
    return safe_json_save('user_points.json', points_data)

# Günlük bonus için zaman kontrolü (24 saat)
def check_daily_bonus(username):
    points = load_points()
    if username not in points:
        return True, 0  # Kullanıcı ilk kez giriş yapıyorsa bonus hakkı var

    # Kullanıcının son günlük bonus aldığı zamanı kontrol et
    last_bonus_time = points[username].get("last_daily_bonus_time", 0)
    current_time = time.time()

    # 24 saat = 86400 saniye
    time_diff = current_time - last_bonus_time
    if time_diff >= 86400 or last_bonus_time == 0:
        return True, 0

    # Kalan süreyi hesapla (saniye cinsinden)
    remaining_seconds = 86400 - time_diff
    return False, remaining_seconds

# Günlük bonus verme
async def give_daily_bonus(username, bot=None):
    blacklist = load_blacklist()
    if username in blacklist:
        return False, "Maalesef kara listede olduğunuz için bonus alamazsınız."

    can_get_bonus, remaining_seconds = check_daily_bonus(username)

    if not can_get_bonus:
        hours = int(remaining_seconds // 3600)
        minutes = int((remaining_seconds % 3600) // 60)
        return False, f"Günlük bonusunuzu zaten aldınız! {hours} saat {minutes} dakika sonra tekrar alabilirsiniz."

    points = load_points()
    if username not in points:
        points[username] = {
            "points": 0,
            "last_update": time.time(),
            "last_seen": time.time(),
            "is_active": True
        }

    # Bonus ekle
    points[username]["points"] += 100
    points[username]["last_daily_bonus_time"] = time.time()  # Unix timestamp olarak kaydet
    save_points(points)

    # Bot üzerinden bildirim yollayacağız, burada mesaj oluşturma yeterli
    return True, f"Günlük bonus başarıyla verildi: +100 Coin! Toplam: {points[username]['points']}"

def add_points(username, amount):
    """Shop satın alımları için puan ekleme fonksiyonu"""
    max_retries = 3
    retry_count = 0

    while retry_count < max_retries:
        try:
            with _points_lock:
                points = load_points()

                if username not in points:
                    points[username] = {
                        "points": 0,
                        "last_update": time.time(),
                        "last_seen": time.time(),
                        "is_active": True
                    }

                points[username]["points"] += amount
                points[username]["last_update"] = time.time()

                if save_points(points):
                    return True
                else:
                    retry_count += 1
                    time.sleep(0.1)
        except Exception as e:
            print(f"Error adding points to {username} (attempt {retry_count + 1}): {e}")
            retry_count += 1
            time.sleep(0.1)

    print(f"Failed to add points for {username} after {max_retries} attempts")
    return False

async def update_user_points(username, bot=None):
    blacklist = load_blacklist()
    if not bot or username == "MistavaMusic" or username in blacklist:  # Bot'un kendine veya haricilere puan vermesini engelle
        return 0

    points = load_points()
    points_added = 0

    # Tüm kullanıcıların listesini al
    all_users = list(points.keys())

    try:
        # Odadaki kullanıcıları kontrol et
        room_users = (await bot.highrise.get_room_users()).content
        user_in_room = any(user.username == username for user, _ in room_users)

        current_time = time.time()

        if username not in points:
            points[username] = {
                "points": 0,
                "last_update": current_time - 600,  # Kullanıcı ilk girdiğinde hemen puan alabilsin
                "last_seen": current_time if user_in_room else 0,
                "is_active": user_in_room
            }
            # İlk kayıt olduğunda kullanıcıya bildirim gönder
            try:
                if user_in_room:
                    user_id = next(user.id for user, _ in room_users if user.username == username)
                    await bot.highrise.send_whisper(user_id, f"💰 Coin sistemine hoş geldiniz! Odada geçirdiğiniz her 10 dakika için otomatik olarak 10 coin kazanacaksınız.")
            except Exception as e:
                print(f"İlk bildirim gönderme hatası: {e}")

        # Kullanıcının aktivite durumunu güncelle
        old_status = points[username].get("is_active", False)
        points[username]["is_active"] = user_in_room

        if user_in_room:
            # Kullanıcı odadaysa
            if "last_seen" not in points[username]:
                points[username]["last_seen"] = current_time

            # Son güncelleme zamanından beri geçen süre
            time_diff = current_time - points[username]["last_update"]

            # Kullanıcı uzun süre inaktiften sonra geri geldiyse, tek bir ödül ver
            if "last_seen" in points[username] and (current_time - points[username]["last_seen"]) > 600:  # 10 dakikadan fazla yoksa
                # Kullanıcıya sadece bir kez puan ver ve zamanı güncelle
                points_to_add = 10
                points[username]["points"] += points_to_add
                points[username]["last_update"] = current_time
                points_added = points_to_add

                # Kullanıcıya hoş geldin bildirimi gönder
                try:
                    user_id = next(user.id for user, _ in room_users if user.username == username)
                    await bot.highrise.send_whisper(user_id, f"🎉 Tekrar hoş geldiniz! +{points_to_add} Coin kazandınız! Toplam Coin: {points[username]['points']}")
                except Exception as e:
                    print(f"Hoş geldin bildirimi hatası: {e}")
            # Normal periyodik ödül kontrolü
            elif time_diff >= 600:  # 10 dakika = 600 saniye
                points_to_add = 10  # Her 10 dakikada 10 puan
                points[username]["points"] += points_to_add
                points[username]["last_update"] = current_time
                points_added = points_to_add

                # Kullanıcıya puan bildirimi gönder
                try:
                    user_id = next(user.id for user, _ in room_users if user.username == username)
                    await bot.highrise.send_whisper(user_id, f"✨ +{points_to_add} Coin kazandınız! Toplam Coin: {points[username]['points']}")
                except Exception as e:
                    print(f"Bildirim gönderme hatası: {e}")

            # Son görülme zamanını güncelle
            points[username]["last_seen"] = current_time
        else:
            # Kullanıcı odada değilse
            if points[username].get("is_active", False):
                # Aktif durumdan inaktif duruma geçiyorsa log ekle
                print(f"Kullanıcı odadan çıktı: {username}")

            # Son görülme zamanını sıfırla ve is_active'i false olarak ayarla
            points[username]["last_seen"] = 0
            points[username]["is_active"] = False

        # Her durumda değişiklikleri kaydet
        save_points(points)
    except Exception as e:
        print(f"Error updating points: {e}")

    return points[username]["points"]

def get_user_points(username):
    points = load_points()
    return points.get(username, {}).get("points", 0)

def deduct_points(username, amount):
    points = load_points()
    if username in points and points[username]["points"] >= amount:
        points[username]["points"] -= amount
        save_points(points)
        return True
    return False

def use_points(username, amount):
    max_retries = 3
    retry_count = 0

    while retry_count < max_retries:
        try:
            with _points_lock:
                points = load_points()
                if username in points and points[username]["points"] >= amount:
                    points[username]["points"] -= amount
                    if save_points(points):
                        return True
                    else:
                        retry_count += 1
                        time.sleep(0.1)
                else:
                    return False
        except Exception as e:
            print(f"Error using points for {username} (attempt {retry_count + 1}): {e}")
            retry_count += 1
            time.sleep(0.1)

    print(f"Failed to use points for {username} after {max_retries} attempts")
    return False

def check_top_command_usage(username, vip_level):
    """Top komutunun günlük kullanım hakkını kontrol eder"""
    from datetime import datetime
    import time

    points = load_points()
    today = datetime.now().strftime("%Y-%m-%d")

    if username not in points:
        points[username] = {
            "points": 0,
            "last_update": time.time(),
            "last_seen": time.time(),
            "is_active": False
        }

    # Günlük kullanım anahtarı
    usage_key = f"top_usage_{today}"
    current_usage = points[username].get(usage_key, 0)

    # VIP seviyesine göre günlük limit
    daily_limit = 3 if vip_level == 3 else 2  # Kademe 3: 3 hak, Kademe 2: 2 hak

    if current_usage >= daily_limit:
        return False, current_usage, daily_limit

    return True, current_usage, daily_limit

def use_top_command(username):
    """Top komutunu kullandıktan sonra sayacı artırır"""
    from datetime import datetime

    points = load_points()
    today = datetime.now().strftime("%Y-%m-%d")

    if username not in points:
        return False

    usage_key = f"top_usage_{today}"
    current_usage = points[username].get(usage_key, 0)
    points[username][usage_key] = current_usage + 1

    save_points(points)
    return True

def reset_top_usage(username):
    """Daily bonus alındığında top komut hakkını sıfırlar (VIP'ler için)"""
    from datetime import datetime

    points = load_points()
    today = datetime.now().strftime("%Y-%m-%d")

    if username not in points:
        return False

    usage_key = f"top_usage_{today}"
    points[username][usage_key] = 0

    save_points(points)
    return True