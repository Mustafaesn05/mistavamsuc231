import ffmpeg
import yt_dlp as youtube_dl
import os
from highrise import BaseBot, SessionMetadata, User, Position, Item, CurrencyItem
from highrise.__main__ import *
from threading import Thread
import time
import asyncio
import threading
import random
from flask import Flask
from concurrent.futures import ThreadPoolExecutor
import os
import gc

# Enable automatic garbage collection with optimized settings
gc.enable()
# Set garbage collection threshold (generation0, generation1, generation2)
gc.set_threshold(1000, 15, 10)  # Daha yüksek eşik değerleri
# Disable gc debug flags for better performance
gc.set_debug(0)
# Initial collection
gc.collect()

# Periyodik gc collection için fonksiyon
async def periodic_gc():
    while True:
        await asyncio.sleep(300)  # Her 5 dakikada bir
        gc.collect()
# Web Server for keeping the bot alive

class WebServer():
    def __init__(self):
        self.app = Flask(__name__)

        @self.app.route('/')
        def index() -> str:
            return "Alive"

    def run(self) -> None:
        self.app.run(host='0.0.0.0', port=8080)

    def keep_alive(self):
        t = Thread(target=self.run)
        t.start()

# Bot for interacting with Highrise API
class MyBot(BaseBot):
    def __init__(self):
        super().__init__()
        from queue_manager import load_queue
        from admin_manager import load_admins
        from vip_manager import load_vips
        self.queue = load_queue()  # Load queue from JSON
        self.admins = load_admins()  # Load admin list
        self.vips = load_vips()  # Load VIP list
        self.current_song = None
        self.current_song_username = None
        self.is_playing = False
        self.current_thread = None
        self.should_stop = False
        self.searching_users = set()  # Şarkı arayan kullanıcıları takip etmek için
        self.dance_running = False

        from emotes_data import load_current_emote
        self.current_emote = load_current_emote()

    def get_user_vip_level(self, username):
        """Kullanıcının VIP seviyesini döndürür. VIP değilse 0 döner."""
        from vip_manager import get_user_vip_level
        return get_user_vip_level(username)

    def is_vip(self, username):
        """Kullanıcının herhangi bir VIP seviyesinde olup olmadığını kontrol eder"""
        return self.get_user_vip_level(username) > 0

    def is_admin(self, username):
        from admin_manager import load_admins
        self.admins = load_admins()  # Her kontrol edildiğinde listeyi yeniden yükle
        return username in self.admins if self.admins is not None else False

    async def on_user_left(self, user: User) -> None:
        await self.save_room_users()

    async def on_user_join(self, user: User, position) -> None:
        await self.save_room_users()

    async def on_start(self, session_metadata: SessionMetadata) -> None:
        print("hi im alive?")
        self.user_id = session_metadata.user_id  # Bot'un kendi ID'sini kaydet

        # WebSocket bağlantı ayarlarını iyileştir
        if hasattr(self.highrise, '_websocket') and self.highrise._websocket:
            # Ping/pong ayarları
            self.highrise._websocket.ping_interval = 20  # 20 saniyede bir ping gönder
            self.highrise._websocket.ping_timeout = 10   # 10 saniye ping timeout
            self.highrise._websocket.close_timeout = 10  # 10 saniye close timeout
            
        # Leave check task'i başlat
        #self.leave_check_task = asyncio.create_task(self.check_left_users())
        try:
            await self.highrise.tg.create_task(self.highrise.teleport(
                session_metadata.user_id, Position(16, 0.25, 16, "FrontLeft")))
        except Exception as e:
            print(f"Teleport error: {e}")
            # Teleport başarısız olursa devam et

        # Bot için floss dansı döngüsünü başlat
        async def dance_loop():
            from emotes_data import paid_emotes
            self.dance_running = True
            while self.dance_running:
                try:
                    if not self.dance_running:
                        break

                    if self.current_emote:
                        # Belirli bir emote seçildiyse, sürekli onu tekrarla
                        emote_data = next((data for name, data in paid_emotes.items() if data["value"] == self.current_emote), None)
                        if emote_data:
                            max_retries = 3
                            retry_count = 0
                            while retry_count < max_retries:
                                try:
                                    await self.highrise.send_emote(self.current_emote, None)
                                    await asyncio.sleep(emote_data["time"])
                                    break  # Başarılı olursa döngüden çık
                                except Exception as e:
                                    retry_count += 1
                                    print(f"Emote kullanma hatası (Deneme {retry_count}/{max_retries}): {e}")
                                    await asyncio.sleep(2)  # Hata durumunda bekle
                            if retry_count == max_retries:
                                print("Maksimum deneme sayısına ulaşıldı, bir sonraki emote'a geçiliyor")
                                await asyncio.sleep(5)  # Daha uzun bir bekleme süresi
                        else:
                            await asyncio.sleep(2)
                    else:
                        # current_emote boşsa hiç emote yapma, sadece bekle
                        await asyncio.sleep(5)

                except Exception as e:
                    print(f"Dans döngüsü hatası: {e}")
                    await asyncio.sleep(2)  # Hata durumunda kısa bekleme

        # Dans döngüsünü başlat
        asyncio.create_task(dance_loop())

        # Sıradaki müzikleri başlatma mekanizması
        if self.queue and not self.is_playing:
            first_song = self.queue[0]
            await self.play_song_with_info(*first_song)

        # Puan güncelleme döngüsünü başlat
        async def point_update_loop():
            while True:
                try:
                    # Önce odadaki tüm kullanıcıları kontrol et ve aktiflik durumlarını güncelle
                    from points_manager import update_user_points
                    await update_user_points("check_all_users", self)

                    # Sonra odadaki aktif kullanıcılara puan ver
                    try:
                        # Timeout ile room users bilgisini al
                        room_users_response = await asyncio.wait_for(
                            self.highrise.get_room_users(), 
                            timeout=15.0
                        )
                        if hasattr(room_users_response, 'content'):
                            room_users = room_users_response.content
                            for user, _ in room_users:
                                if user.username != "MistavaMusic":  # Bot kendisine puan vermesin
                                    await update_user_points(user.username, self)
                        else:
                            print("Error: get_room_users() response has no content attribute")
                    except asyncio.TimeoutError:
                        print("Timeout getting room users for points update")
                    except Exception as e:
                        print(f"Error getting room users for points update: {e}")
                except Exception as e:
                    print(f"Error in point update loop: {e}")
                await asyncio.sleep(60)  # Her dakika kontrol et

        # Bilgilendirme mesaj döngüsünü başlat
        async def info_message_loop():
            messages = [
                "⚠️ Üzgünüz! Teknik bir hata nedeniyle ⭐ favoriler, 🪙 coinler ve 🎁 hediyeler sıfırlandı. Telafi için çalışıyoruz. Anlayışınız için teşekkürler 💖",
                "ℹ️ Komutları görmek için `-help` yazabilirsiniz. Tüm komutların listesi biyografimde mevcuttur.",
                "🎵 Şarkı açmak için `-p şarkıadı` yazabilirsiniz. Örnek: -p Tarkan Kuzu Kuzu",
                "💰 Her 10 dakikada bir otomatik olarak 10 coin kazanabilirsiniz!",
                "🎁 Günlük bonusunuzu almak için `-daily` yazabilirsiniz.",
                "🎵 Sıradaki şarkıları görmek için `-q` yazabilirsiniz.",
                "💝 Çalan şarkıyı favorilerinize eklemek için `-fav` yazabilirsiniz.",
                "⭐ Şuan da çalan şarkıyı puanlamak için '-rate <1-10>' yazabilirsiniz.",
                "📈 En yüksek puan alan şarkıları görmek için 'ratelb' yazabilirsiniz.",
                "🛒 DM'den bana '-shop' yazarak alışveriş yapabilir, Gold göndererek Bakiye Kazanabilirsiniz.",
                "💎 Shop'tan Gold ile Coin satın alabilir, VIP paketleri alabilirsiniz!",
                "✨ VIP olmak için bana Gold gönderin ve DM'den '-shop' yazın!"
            ]
            # Rastgele bir mesajla başla
            message_index = random.randint(0, len(messages) - 1)
            while True:
                try:
                    # Chat mesajları için timeout ekle
                    await asyncio.wait_for(
                        self.highrise.chat(messages[message_index]), 
                        timeout=10.0
                    )
                    message_index = (message_index + 1) % len(messages)
                except asyncio.TimeoutError:
                    print("Timeout sending info message")
                    message_index = (message_index + 1) % len(messages)
                except Exception as e:
                    print(f"Error in info message loop: {e}")
                await asyncio.sleep(45)  # Her 45 saniyede bir mesaj gönder

        # WebSocket bağlantı sağlığını kontrol etme döngüsü
        async def connection_health_check():
            while True:
                try:
                    # Her 30 saniyede bir basit bir API çağrısı yaparak bağlantıyı test et
                    await asyncio.sleep(30)
                    if hasattr(self.highrise, 'get_room_users'):
                        try:
                            await asyncio.wait_for(self.highrise.get_room_users(), timeout=10.0)
                        except asyncio.TimeoutError:
                            print("Connection health check timeout - connection may be unstable")
                        except Exception as e:
                            print(f"Connection health check failed: {e}")
                except Exception as e:
                    print(f"Error in connection health check: {e}")

        # Tüm asenkron görevleri başlat
        asyncio.create_task(point_update_loop())
        asyncio.create_task(info_message_loop())
        asyncio.create_task(periodic_gc())  # Periyodik GC'yi başlat
        asyncio.create_task(self.check_left_users_periodically())  # Kullanıcı kontrol döngüsü
        asyncio.create_task(connection_health_check())  # Bağlantı sağlık kontrolü

    async def save_room_users(self):
        try:
            import json
            room_users_response = await self.highrise.get_room_users()
            if hasattr(room_users_response, 'content'):
                room_users = room_users_response.content
                user_list = [{"username": user.username, "id": user.id} for user, _ in room_users]
                with open('players.json', 'w', encoding='utf-8') as f:
                    json.dump({"users": user_list}, f, ensure_ascii=False, indent=4)
            else:
                print("Error: get_room_users() response has no content attribute")
        except Exception as e:
            print(f"Error saving room users: {e}")

    async def check_left_users_periodically(self):
        """Periyodik olarak kullanıcıları kontrol eder ve çıkanların şarkılarını 3 dakika sonra siler"""
        await asyncio.sleep(30)
        user_left_times = {}  # Kullanıcıların çıkış zamanlarını takip et

        while True:
            try:
                room_users_response = await self.highrise.get_room_users()
                if hasattr(room_users_response, 'content'):
                    current_users = {user.username for user, _ in room_users_response.content}
                    users_in_queue = {song[3] for song in self.queue if len(song) > 3}
                    users_to_remove = users_in_queue - current_users

                    # Yeni çıkan kullanıcıları tespit et ve zamanlarını kaydet
                    for username in users_to_remove:
                        if username not in user_left_times:
                            user_left_times[username] = time.time()

                    # 3 dakika geçen kullanıcıların şarkılarını sil
                    current_time = time.time()
                    for username in list(user_left_times.keys()):
                        if current_time - user_left_times[username] >= 180:  # 3 dakika = 180 saniye
                            songs_to_remove = [song for song in self.queue if song[3] == username]

                            if songs_to_remove:
                                self.queue = [song for song in self.queue if song[3] != username]
                                from queue_manager import save_queue
                                save_queue(self.queue)

                            # Kullanıcıyı takip listesinden çıkar
                            del user_left_times[username]

                    # Geri dönen kullanıcıları takip listesinden çıkar
                    for username in list(user_left_times.keys()):
                        if username in current_users:
                            del user_left_times[username]

                    await self.save_room_users()

            except Exception as e:
                pass

            await asyncio.sleep(20)

    async def on_chat(self, user: User, message: str) -> None:
        from points_manager import load_points, save_points
        if message == "users":
            room_users = (await self.highrise.get_room_users()).content
            await self.highrise.chat(f"👥 Odada {len(room_users)} kullanıcı var.")
            await self.save_room_users()
            return
        # Admin komutları
        if message.startswith("-addadmin @") and self.is_admin(user.username):
            room_users = (await self.highrise.get_room_users()).content
            new_admin = message[10:].strip().replace('@', '')
            user_exists = any(user.username == new_admin for user, _ in room_users)

            if user_exists:
                if new_admin not in self.admins:
                    from admin_manager import save_admins, load_admins
                    self.admins.append(new_admin)
                    if save_admins(self.admins):
                        self.admins = load_admins()  # Yeniden yükle
                        await self.highrise.chat(f"✅ @{new_admin} yönetici olarak eklendi.")
                    else:
                        self.admins.remove(new_admin)
                        await self.highrise.chat("❌ Yönetici eklenirken bir hata oluştu!")
                else:
                    await self.highrise.chat(f"❌ @{new_admin} zaten bir yönetici!")
            else:
                await self.highrise.chat(f"❌ @{new_admin} odada bulunamadı!")
            return

        elif message.startswith("-removeadmin @") and self.is_admin(user.username):
            admin_to_remove = message[12:].strip().replace('@', '')
            if admin_to_remove in self.admins:
                if admin_to_remove != user.username:
                    from admin_manager import save_admins, load_admins
                    self.admins.remove(admin_to_remove)
                    if save_admins(self.admins):
                        self.admins = load_admins()  # Yeniden yükle
                        await self.highrise.chat(f"❌ @{admin_to_remove} yönetici listesinden kaldırıldı.")
                    else:
                        self.admins.append(admin_to_remove)
                        await self.highrise.chat("❌ Yönetici kaldırılırken bir hata oluştu!")
                else:
                    await self.highrise.chat("❌ Kendinizi yönetici listesinden kaldıramazsınız!")
            else:
                await self.highrise.chat(f"❌ @{admin_to_remove} yönetici listesinde bulunamadı!")
            return

        elif message == "-admins" and self.is_admin(user.username):
            admin_list = [f"@{admin}" for admin in self.admins]
            # Send admins in chunks of 5
            for i in range(0, len(admin_list), 5):
                 chunk = admin_list[i:i+5]
                 await self.highrise.send_whisper(user.id, f"👑 Adminler ({i+1}-{min(i+5, len(admin_list))}): {', '.join(chunk)}")
        if message in ["-queue", "-q"]:
            if not self.queue and not self.current_song:
                await self.highrise.send_whisper(user.id, "📝 Sırada şarkı yok")
                return

            await self.highrise.send_whisper(user.id, "🎵 Sıradaki şarkılar:")
            for i, (_, title, duration, username) in enumerate(self.queue, 1):
                minutes = duration // 60
                seconds = duration % 60
                await self.highrise.send_whisper(user.id, f"{i}. {title} [{minutes}:{seconds:02d}]\n\n👤 ekleyen : @{username}")
            return

        elif message in ["-n", "-np"]:
            if self.current_song:
                await self.highrise.send_whisper(user.id, f"🎵 Şu an çalıyor: {self.current_song}\n👤 İsteyen: @{self.current_song_username}")
            else:
                await self.highrise.send_whisper(user.id, "❌ Şu anda çalan şarkı yok")
            return

        elif message == "-m":
            from user_stats import load_user_stats
            stats = load_user_stats()
            user_songs = [(i, song) for i, song in enumerate(self.queue) if song[3] == user.username]
            song_count = stats.get(user.username, {}).get("song_requests", 0)

            await self.highrise.send_whisper(user.id, f"📊 @{user.username} toplam {song_count} şarkı istedi.")
            if user_songs:
                await self.highrise.send_whisper(user.id, f"🎵 Şarkılarınız ({len(user_songs)}):")
                for user_song_index, (queue_index, (_, title, duration, _)) in enumerate(user_songs, 1):
                    minutes = duration // 60
                    seconds = duration % 60
                    queue_position = queue_index + 1  # Sıradaki pozisyon (1'den başlar)
                    await self.highrise.send_whisper(user.id, f"{user_song_index}. {title} [{minutes}:{seconds:02d}] (Sıra #{queue_position})")
            else:
                await self.highrise.send_whisper(user.id, "❌ Sırada şarkın yok.")
            return

        elif message == "-clear":
            if not self.is_admin(user.username):
                await self.highrise.send_whisper(user.id, f"❌ @{user.username} Bu komutu kullanma yetkin yok!")
                return
            self.queue = []
            from queue_manager import save_queue
            save_queue([])
            await self.highrise.send_whisper(user.id, "🗑️ Sıra temizlendi.")
            return

        elif message.startswith("-remove "):
            if not self.is_admin(user.username):
                await self.highrise.send_whisper(user.id, f"❌ @{user.username} Bu komutu kullanma yetkiniz yok!")
                return
            try:
                index = int(message[8:].strip()) - 1
                if 0 <= index < len(self.queue):
                    removed_song = self.queue.pop(index)
                    from queue_manager import save_queue
                    save_queue(self.queue)
                    await self.highrise.send_whisper(user.id, f"❌ Sıradan çıkarıldı: {removed_song[1]}")
                else:
                    await self.highrise.send_whisper(user.id, "❌ Geçersiz sıra numarası")
            except ValueError:
                await self.highrise.send_whisper(user.id, "❌ Lütfen geçerli bir sayı girin")
            return

        elif message.startswith("-del"):
            user_songs = [(i, song) for i, song in enumerate(self.queue) if song[3] == user.username]
            if not user_songs:
                await self.highrise.send_whisper(user.id, "❌ Eklediğiniz şarkı sırada değil!")
                return

            message_parts = message.split()
            if len(message_parts) > 1:  # Has number after -del
                try:
                    song_num = int(message_parts[1]) - 1
                    if 0 <= song_num < len(user_songs):
                        index, removed_song = user_songs[song_num]
                        self.queue.pop(index)
                        from queue_manager import save_queue
                        save_queue(self.queue)
                        await self.highrise.send_whisper(user.id, f"❌ @{user.username} şarkısını sıradan kaldırdı: {removed_song[1]}")
                    else:
                        await self.highrise.send_whisper(user.id, f"❌ Geçersiz şarkı numarası!")
                        await self.highrise.send_whisper(user.id, "🎵 Şarkılarınız:")
                        for i, (_, song) in enumerate(user_songs):
                            await self.highrise.send_whisper(user.id, f"{i+1}. {song[1]}")
                except (ValueError, IndexError):
                    await self.highrise.send_whisper(user.id, "❌ Geçersiz komut! Kullanım: -del <numara>")
            else:
                if len(user_songs) == 1:
                    index, removed_song = user_songs[0]
                    self.queue.pop(index)
                    from queue_manager import save_queue
                    save_queue(self.queue)
                    await self.highrise.send_whisper(user.id, f"❌ @{user.username} şarkısını sıradan kaldırdı: {removed_song[1]}")
                else:
                    await self.highrise.send_whisper(user.id, f"❌ Birden fazla şarkınız var! Kullanım: -del <numara>")
                    await self.highrise.send_whisper(user.id, "🎵 Şarkılarınız:")
                    for i, (_, song) in enumerate(user_songs):
                        await self.highrise.send_whisper(user.id, f"{i+1}. {song[1]}")
            return

        elif message.startswith("-p"):
            # Hariciler listesini kontrol et
            from blacklist_manager import load_blacklist
            blacklist = load_blacklist()
            if user.username in blacklist:
                await self.highrise.send_whisper(user.id, f"❌ @{user.username} Kara listede olduğunuz için şarkı ekleyemezsiniz!")
                return

            if len(message) < 3 or message[2] != ' ':
                await self.highrise.send_whisper(user.id, "❌ Yanlış komut kullanımı! Doğru kullanım: -p <şarkı adı>")
                return

            song_name = message[len("-p "):].strip()
            if len(song_name) < 3:
                await self.highrise.send_whisper(user.id, "❌ Bir şarkı aramak için en az 3 karakter girmelisiniz!")
                return

            # Check user's songs in queue with new VIP system
            user_songs = len([song for song in self.queue if song[3] == user.username])

            # Determine max songs based on VIP level
            from vip_manager import get_max_songs_for_user
            max_songs = get_max_songs_for_user(user.username, self.is_admin(user.username))

            if user_songs >= max_songs:
                vip_level = self.get_user_vip_level(user.username)
                if self.is_admin(user.username):
                    role = "👑 Admin"
                    limit_text = "unlimited"
                elif vip_level > 0:
                    from vip_manager import get_vip_emoji
                    role = f"{get_vip_emoji(vip_level)} Kademe {vip_level} VIP"
                    limit_text = str(max_songs)
                else:
                    role = "Normal"
                    limit_text = str(max_songs)

                await self.highrise.send_whisper(user.id, f"❌ @{user.username} ({role}) kullanıcıları sıraya en fazla {limit_text} şarkı ekleyebilir!")
                return

            await self.highrise.send_whisper(user.id, f"🔍 Şarkı aranıyor: {song_name}")

            try:
                # Asenkron şarkı araması
                song_info = await self.search_youtube(song_name)

                if song_info:
                    # Yasaklı şarkı kontrolü
                    from blocked_songs_manager import load_blocked_songs
                    blocked_songs = load_blocked_songs()
                    if song_info[1] in blocked_songs:
                        await self.highrise.send_whisper(user.id, "❌ Bu şarkı kara listede olduğu için çalınamaz!")
                        return

                    # Şarkı süresi kontrolü (minimum 60 saniye, maksimum 7 dakika)
                    min_duration = 60  # 60 saniye
                    max_duration = 480  # 7 dakika
                    song_duration = song_info[2]  # duration (saniye cinsinden)

                    # Minimum süre kontrolü (admin dahil tüm kullanıcılar için)
                    if song_duration < min_duration:
                        await self.highrise.send_whisper(user.id, f"❌ Şarkı çok kısa! En az {min_duration} saniye uzunluğunda şarkılar çalabilirsiniz. Bu şarkı {song_duration} saniye uzunluğunda.")
                        return

                    # Admin kullanıcılar için süre limiti yok, diğer kullanıcılar için 7 dakika limit
                    if not self.is_admin(user.username) and song_duration > max_duration:
                        minutes = max_duration // 60
                        seconds = max_duration % 60
                        song_minutes = song_duration // 60
                        song_seconds = song_duration % 60
                        await self.highrise.send_whisper(user.id, f"❌ Şarkı çok uzun! En fazla {minutes}:{seconds:02d} dakika uzunluğunda şarkılar çalabilirsiniz. Bu şarkı {song_minutes}:{song_seconds:02d} uzunluğunda.")
                        return

                    if self.is_playing:
                        # Check if song is already in queue
                        duplicate_song = next((song for song in self.queue if song[1].lower() == song_info[1].lower()), None)
                        if duplicate_song:
                            duplicate_user = duplicate_song[3]
                            await self.highrise.send_whisper(user.id, f"❌ Bu şarkı zaten @{duplicate_user} tarafından sıraya eklendi!")
                            return

                        song_with_user = (*song_info, user.username)  # URL, title, duration, username
                        self.queue.append(song_with_user)
                        from queue_manager import save_queue
                        save_queue(self.queue)
                        queue_position = len(self.queue)

                        # VIP emoji gösterimi
                        vip_level = self.get_user_vip_level(user.username)
                        admin_emoji = "👑 " if self.is_admin(user.username) else ""
                        vip_emoji = ""
                        if vip_level > 0 and not self.is_admin(user.username):
                            from vip_manager import get_vip_emoji
                            vip_emoji = f"{get_vip_emoji(vip_level)} "

                        await self.highrise.chat(f"🎵 @{user.username} {admin_emoji}{vip_emoji} sıraya eklendi (Pozisyon #{queue_position}):\n\n{song_info[1]}")
                    else:
                        song_with_user = (*song_info, user.username)
                        self.queue.append(song_with_user)
                        await self.play_song_with_info(song_info[0], song_info[1], song_info[2], user.username)
            except Exception as e:
                await self.highrise.chat("Şarkı Bulunamadı veya Bir Sorun Var")
                print(f"Error: {e}")

        elif message.startswith("-addvip @") and self.is_admin(user.username):
            room_users = (await self.highrise.get_room_users()).content

            # Parse the command to get username and level
            parts = message[8:].strip().split()
            if len(parts) < 2:
                await self.highrise.send_whisper(user.id, "❌ Kullanım: -addvip @kullanıcı <seviye>\nSeviyeler: 1 (⭐), 2 (🌟), 3 (💎)")
                return

            new_vip = parts[0].replace('@', '')
            try:
                level = int(parts[1])
                if level not in [1, 2, 3]:
                    await self.highrise.send_whisper(user.id, "❌ Geçersiz seviye! Seviyeler: 1 (⭐), 2 (🌟), 3 (💎)")
                    return
            except ValueError:
                await self.highrise.send_whisper(user.id, "❌ Lütfen geçerli bir seviye numarası girin (1, 2, 3)")
                return

            user_exists = any(user.username == new_vip for user, _ in room_users)

            if user_exists:
                from vip_manager import add_vip, get_vip_emoji
                if add_vip(new_vip, level):
                    emoji = get_vip_emoji(level)
                    await self.highrise.send_whisper(user.id, f"✨ @{new_vip} Kademe {level} VIP {emoji} olarak eklendi")
                else:
                    await self.highrise.send_whisper(user.id, "❌ VIP eklenirken bir hata oluştu!")
            else:
                await self.highrise.send_whisper(user.id, f"❌ @{new_vip} odada bulunamadı!")
            return

        elif message.startswith("-removevip @") and self.is_admin(user.username):
            vip_to_remove = message[11:].strip().replace('@', '')

            from vip_manager import remove_vip, get_user_vip_level
            old_level = get_user_vip_level(vip_to_remove)

            if old_level > 0:
                if remove_vip(vip_to_remove):
                    await self.highrise.send_whisper(user.id, f"❌ @{vip_to_remove} VIP listesinden kaldırıldı.")
                else:
                    await self.highrise.send_whisper(user.id, "❌ VIP kaldırılırken bir hata oluştu!")
            else:
                await self.highrise.send_whisper(user.id, f"❌ @{vip_to_remove} VIP listesinde bulunamadı!")
            return

        elif message == "-vips" and (self.is_admin(user.username) or self.is_vip(user.username)):
            from vip_manager import load_vips, get_vip_emoji
            vips = load_vips()

            all_vips = []
            for level in [1, 2, 3]:
                level_key = f"level_{level}"
                for vip_user in vips.get(level_key, []):
                    emoji = get_vip_emoji(level)
                    all_vips.append(f"@{vip_user} {emoji}")

            if not all_vips:
                await self.highrise.send_whisper(user.id, "📝 VIP listesi boş!")
                return

            # Send VIPs in chunks of 5
            for i in range(0, len(all_vips), 5):
                chunk = all_vips[i:i+5]
                await self.highrise.send_whisper(user.id, f"✨ VIPs ({i+1}-{min(i+5, len(all_vips))}): {', '.join(chunk)}")

        elif message.startswith("-top") and (self.is_admin(user.username) or self.get_user_vip_level(user.username) >= 2):
            # Önce şarkı kontrolü yap
            user_songs = [(i, song) for i, song in enumerate(self.queue) if song[3] == user.username]

            if not user_songs:
                await self.highrise.send_whisper(user.id, "❌ Sırada hiç şarkınız yok!")
                return

            # Birden fazla şarkı varsa ve numara verilmemişse, hak kullanmadan uyar
            args = message.split()
            if len(user_songs) > 1 and len(args) == 1:
                await self.highrise.send_whisper(user.id, f"❌ Birden fazla şarkınız var! Doğru kullanım: -top <şarkı numarası>")
                await self.highrise.send_whisper(user.id, "🎵 Şarkılarınız:")
                for i, (_, song) in enumerate(user_songs):
                    await self.highrise.send_whisper(user.id, f"{i+1}. {song[1]}")
                return

            # Geçersiz numara kontrolü (hak kullanmadan önce)
            if len(user_songs) > 1 and len(args) > 1:
                try:
                    song_number = int(args[1]) - 1
                    if not (0 <= song_number < len(user_songs)):
                        songs_list = "\n".join([f"{i+1}. {song[1]}" for i, (_, song) in enumerate(user_songs)])
                        await self.highrise.send_whisper(user.id, f"❌ Geçersiz şarkı numarası! Şarkılarınız:\n{songs_list}")
                        return
                except (IndexError, ValueError):
                    songs_list = "\n".join([f"{i+1}. {song[1]}" for i, (_, song) in enumerate(user_songs)])
                    await self.highrise.send_whisper(user.id, f"❌ Lütfen bir şarkı numarası girin:\n{songs_list}")
                    return

            # Tüm kontroller geçtikten sonra VIP kullanım hakkı kontrolü
            vip_level = self.get_user_vip_level(user.username)
            if not self.is_admin(user.username):
                from points_manager import check_top_command_usage, use_top_command

                can_use, current_usage, daily_limit = check_top_command_usage(user.username, vip_level)

                if not can_use:
                    await self.highrise.send_whisper(user.id, f"❌ Günlük -top komut hakkınızı ({daily_limit}) kullandınız!")
                    return

                # Kullanım sayısını artır
                use_top_command(user.username)

            # Şarkıyı taşıma işlemi
            if len(user_songs) == 1:
                index, song = user_songs[0]
                if index == 0:
                    await self.highrise.send_whisper(user.id, f"❌ '{song[1]}' zaten sıranın en başında!")
                    return
                # Şarkıyı en başa taşı
                self.queue.insert(0, self.queue.pop(index))
                from queue_manager import save_queue
                save_queue(self.queue)
                await self.highrise.send_whisper(user.id, f"⬆️ '{song[1]}' sıranın başına taşındı!")
            else:
                song_number = int(args[1]) - 1
                index, song = user_songs[song_number]
                if index == 0:
                    await self.highrise.send_whisper(user.id, f"❌ '{song[1]}' zaten sıranın en başında!")
                    return
                # Seçilen şarkıyı en başa taşı
                self.queue.insert(0, self.queue.pop(index))
                from queue_manager import save_queue
                save_queue(self.queue)
                await self.highrise.send_whisper(user.id, f"⬆️ '{song[1]}' sıranın başına taşındı!")
            return

        elif message.startswith("-addblacklist @") and self.is_admin(user.username):
            from blacklist_manager import load_blacklist, save_blacklist
            blacklist = load_blacklist()
            username_to_blacklist = message[14:].strip().replace('@', '')

            if username_to_blacklist not in blacklist:
                blacklist.append(username_to_blacklist)
                if save_blacklist(blacklist):
                    await self.highrise.send_whisper(user.id, f"❌ @{username_to_blacklist} kara listeye eklendi.")
                else:
                    await self.highrise.send_whisper(user.id, "❌ Kara liste kaydedilirken bir hata oluştu!")
            else:
                await self.highrise.send_whisper(user.id, f"❌ @{username_to_blacklist} zaten kara listede!")
            return

        elif message.startswith("-rblacklist @") and self.is_admin(user.username):
            from blacklist_manager import load_blacklist, save_blacklist
            blacklist = load_blacklist()
            username_to_remove = message[12:].strip().replace('@', '')

            if username_to_remove in blacklist:
                blacklist.remove(username_to_remove)
                if save_blacklist(blacklist):
                    await self.highrise.send_whisper(user.id, f"✅ @{username_to_remove} kara listeden kaldırıldı.")
                else:
                    await self.highrise.send_whisper(user.id, "❌ Kara liste kaydedilirken bir hata oluştu!")
            else:
                await self.highrise.send_whisper(user.id, f"❌ @{username_to_remove} kara listede bulunamadı!")
            return

        elif message == "-blacklist" and self.is_admin(user.username):
            from blacklist_manager import load_blacklist
            blacklist = load_blacklist()

            if not blacklist:
                await self.highrise.send_whisper(user.id, "📝 Kara liste Boş.")
            else:
                blacklist_users = [f"@{user}" for user in blacklist]
                # Send blacklist in chunks of 5
                for i in range(0, len(blacklist_users), 5):
                    chunk = blacklist_users[i:i+5]
                    await self.highrise.send_whisper(user.id, f"❌ Blacklist ({i+1}-{min(i+5, len(blacklist_users))}): {', '.join(chunk)}")
            return

        elif message == "-s":
            if not hasattr(self, 'skip_votes'):
                self.skip_votes = set()

            if not self.is_playing:
                await self.highrise.send_whisper(user.id, "❌ Şu anda çalan bir şarkı yok!")
                return

            if user.username in self.skip_votes:
                await self.highrise.send_whisper(user.id, "❌ Zaten oy kullandınız!")
                return

            room_users = (await self.highrise.get_room_users()).content
            # Bot'u saymadan kullanıcı sayısını hesapla
            total_users = sum(1 for user, _ in room_users if user.username != "MistavaMusic")
            required_votes = max(1, round(total_users * 0.6))  # 60% threshold, minimum 1 vote

            self.skip_votes.add(user.username)
            current_votes = len(self.skip_votes)

            if current_votes >= required_votes:
                await self.highrise.chat(f"⏭️ Yeterli oy toplandı ({current_votes}/{required_votes})! Şarkı atlanıyor...")
                self.skip_votes.clear()
                # Update current song info before skipping
                if self.queue:
                    next_song = self.queue[0]
                    self.current_song = next_song[1]  # Update title
                    self.current_song_username = next_song[3]  # Update username
                await self.skip_song()
            else:
                await self.highrise.chat(f"🗳️ Şarkı atlama oyu: {current_votes}/{required_votes} (%{round((current_votes/required_votes)*100)})")
                await self.highrise.send_whisper(user.id, f"🎵 Şu anda çalıyor: {self.current_song}")

        elif message == "-fav":
            if not self.current_song:
                await self.highrise.send_whisper(user.id, "❌ Şu anda çalan bir şarkı yok!")
                return

            from favorites_manager import add_favorite
            current_song_info = {
                "title": self.current_song,
                "added_by": self.current_song_username
            }

            if add_favorite(user.username, current_song_info):
                await self.highrise.send_whisper(user.id, f"💖 {self.current_song} favorilerinize eklendi!")
            else:
                await self.highrise.send_whisper(user.id, "❌ Bu şarkı zaten favorilerinizde!")
            return

        elif message == "-bal":
            from wallet_manager import get_gold
            gold_balance = get_gold(user.username)
            await self.highrise.send_whisper(user.id, f"💰 Wallet Bakiyeniz: {gold_balance} Gold")
            return

        elif message == "-help":
            # Music Commands (in pairs of two commands)
            await self.highrise.send_whisper(user.id, "📋 Müzik Komutları:\n\n-p <şarkı adı> - Şarkıyı çal / sıraya ekle (maksimum 8 dakika)\n-q veya -queue - Şarkı sırasını göster")
            await self.highrise.send_whisper(user.id, "-n - Şu anda çalan şarkıyı göster\n-m - Sıradaki şarkılarını göster")
            await self.highrise.send_whisper(user.id, "-s - Şarkıyı atlamak için oy ver\n-del - Eklediğin son şarkıyı sıradan kaldır")
            await self.highrise.send_whisper(user.id, "-coin - Coin bakiyeni göster\n-up - Sırada bir üst sıraya geç (100 Coin)")

            # Favorite Commands (in pairs of two commands)
            await self.highrise.send_whisper(user.id, "❤️ Favori Komutları:\n\n-fav - Şu anda çalan şarkıyı favorilerine ekle\n-myfav - Favori şarkılarını göster")
            await self.highrise.send_whisper(user.id, "-favs @kullanıcı - Başka bir kullanıcının favorilerini gör\n-delfav <numara> - Favorilerden bir şarkıyı kaldır")

            # Dedication Commands
            await self.highrise.send_whisper(user.id, "🎁 Hediye Komutları:\n\n-g @kullanıcı - Şu anda çalan şarkıyı başka bir kullanıcıya hediye et (50 Coin)\n-myg - Aldığın şarkı hediyelerini göster")

            # Rating Commands
            await self.highrise.send_whisper(user.id, "⭐ Puanlama Komutları:\n\n-rate <1-10> - Şu anda çalan şarkıyı puanla\n-top5 - En yüksek puanlı 5 şarkıyı göster")

            # Other Commands
            await self.highrise.send_whisper(user.id, "📊 Diğer Komutlar:\n\n-lb - Şarkı liderliğini göster\n-coinlb - Coin liderliğini göster")            # Coin Commands
            await self.highrise.send_whisper(user.id, "💰 Coin Komutları:\n\n-coin - Coin bakiyeni göster\n-daily - Günlük 100 coin bonusunu al")
            await self.highrise.send_whisper(user.id, "💎 Wallet Komutları:\n\n-bal - Gold bakiyeni göster\n-shop - Shop menüsünü aç (Gold ile Coin satın al)")

            # VIP help message
            vip_level = self.get_user_vip_level(user.username)
            if vip_level >= 2:
                await self.highrise.send_whisper(user.id, "✨ VIP Komutları:\n\n-top <numara> - Şarkını sıranın en üstüne taşı (Günlük limit)")
            return

        elif message == "-restart":
            if not self.is_admin(user.username):
                await self.highrise.send_whisper(user.id, "❌ Bu komut yalnızca Yönetici kullanıcılar tarafından kullanılabilir!")
                return

            await self.highrise.chat("🔄 Bot yeniden başlatılıyor... Lütfen bekleyin.")
            os._exit(0)  # Programı sonlandır, process manager tarafından otomatik yeniden başlatılacak
            return

        elif message == "-blocklist":
            if not self.is_admin(user.username):
                await self.highrise.send_whisper(user.id, "❌ Bu komut yalnızca yönetici kullanıcılar tarafından kullanılabilir!")
                return

            from blocked_songs_manager import load_blocked_songs
            blocked_songs = load_blocked_songs()

            if not blocked_songs:
                await self.highrise.send_whisper(user.id, "📝 Şarkı kara listesi boş!")
            else:
                await self.highrise.send_whisper(user.id, "🚫 Kara Listeye Alınan Şarkılar:")
                for i, song in enumerate(blocked_songs, 1):
                    await self.highrise.send_whisper(user.id, f"{i}. {song}")
            return

        elif message == "-blocksong":
            if not self.is_admin(user.username):
                await self.highrise.send_whisper(user.id, "❌ Bu komut yalnızca yönetici kullanıcılar tarafından kullanılabilir!")
                return

            if not self.current_song:
                await self.highrise.send_whisper(user.id, "❌ Şu anda çalan bir şarkı yok!")
                return

            from blocked_songs_manager import load_blocked_songs, save_blocked_songs
            blocked_songs = load_blocked_songs()

            if self.current_song in blocked_songs:
                await self.highrise.send_whisper(user.id, "❌ Bu şarkı zaten kara listede!")
                return

            blocked_songs.append(self.current_song)
            if save_blocked_songs(blocked_songs):
                await self.highrise.chat(f"🚫 '{self.current_song}' kara listeye eklendi!")
                await self.skip_song()
            else:
                await self.highrise.send_whisper(user.id, "❌ Şarkıyı kara listeye eklerken bir hata oluştu!")
            return

        elif message.startswith("-unblocksong "):
            if not self.is_admin(user.username):
                await self.highrise.send_whisper(user.id, "❌ Bu komut yalnızca yönetici kullanıcılar tarafından kullanılabilir!")
                return

            try:
                index = int(message.split()[1]) - 1
                from blocked_songs_manager import load_blocked_songs, save_blocked_songs
                blocked_songs = load_blocked_songs()

                if 0 <= index < len(blocked_songs):
                    removed_song = blocked_songs.pop(index)
                    if save_blocked_songs(blocked_songs):
                        await self.highrise.chat(f"✅ '{removed_song}' kara listeden kaldırıldı!")
                    else:
                        blocked_songs.append(removed_song)
                        await self.highrise.send_whisper(user.id, "❌ Şarkıyı kaldırırken bir hata oluştu!")
                else:
                    await self.highrise.send_whisper(user.id, "❌ Geçersiz şarkı numarası!")
            except ValueError:
                await self.highrise.send_whisper(user.id, "❌ Lütfen geçerli bir numara girin!")
            return

        elif message == "-history":
            if not (self.is_admin(user.username) or self.is_vip(user.username)):
                await self.highrise.send_whisper(user.id, "❌ Bu komut yalnızca VIP ve Yönetici kullanıcılar tarafından kullanılabilir!")
                return

            from history_manager import load_history
            history = load_history()

            if not history:
                await self.highrise.send_whisper(user.id, "📝 The song history is empty!")
                return

            await self.highrise.send_whisper(user.id, "🎵 Son Çalınan Şarkılar:")
            for i, song in enumerate(reversed(history), 1):
                minutes = song["duration"] // 60
                seconds = song["duration"] % 60
                await self.highrise.send_whisper(user.id, f"{i}. {song['title']} [{minutes}:{seconds:02d}]\n👤 Requested by: @{song['username'] or 'Unknown'}")

        elif message.startswith("-addcoin @"):
            if user.username != "Mistava":
                await self.highrise.send_whisper(user.id, "❌ Bu komut yalnızca @Mistava tarafından kullanılabilir!")
                return

            try:
                parts = message[9:].split()
                target_username = parts[0].strip().replace('@', '')
                amount = int(parts[1])

                if amount <= 0:
                    await self.highrise.send_whisper(user.id, "❌ Lütfen pozitif bir miktar girin!")
                    return

                points = load_points()
                if target_username not in points:
                    points[target_username] = {
                        "points": 0,
                        "last_update": time.time(),
                        "last_seen": time.time(),
                        "is_active": False
                    }

                points[target_username]["points"] += amount
                save_points(points)

                # Sadece coin gönderilen kişiye bilgi gönder
                room_users = (await self.highrise.get_room_users()).content
                target_user_id = next((user.id for user, _ in room_users if user.username == target_username), None)

                if target_user_id:
                    await self.highrise.send_whisper(target_user_id, f"💰 @Mistava size {amount} coin gönderdi! Yeni bakiyeniz: {points[target_username]['points']}")
                else:
                    await self.highrise.send_whisper(user.id, f"💰 @{target_username} hesabına {amount} coin eklendi! (Kullanıcı şu anda odada değil)")

            except (IndexError, ValueError):
                await self.highrise.send_whisper(user.id, "❌ Geçersiz komut! Kullanım: -addcoin @kullanıcı miktar")
            return

        elif message == "-wallet":
            if user.username not in ["Mistava", "Ilikethewayyoukissme"]:
                await self.highrise.send_whisper(user.id, "❌ Bu komut yalnızca @Mistava ve @Ilikethewayyoukissme tarafından kullanılabilir!")
                return

            try:
                wallet_response = await self.highrise.get_wallet()
                if hasattr(wallet_response, 'content') and wallet_response.content:
                    wallet = wallet_response.content
                    if wallet and len(wallet) > 0:
                        await self.highrise.send_whisper(user.id, f"💰 Bot wallet'ında {wallet[0].amount} {wallet[0].type} bulunuyor")
                    else:
                        await self.highrise.send_whisper(user.id, "💰 Bot wallet'ı boş görünüyor")
                else:
                    await self.highrise.send_whisper(user.id, "❌ Wallet bilgisi alınamadı")
            except Exception as e:
                await self.highrise.send_whisper(user.id, f"❌ Wallet bilgisi alınırken hata oluştu: {str(e)}")
            return

        elif message == "-adminhelp":
            if not self.is_admin(user.username):
                await self.highrise.send_whisper(user.id, "❌ Bu komut yalnızca yönetici kullanıcılar tarafından kullanılabilir!")
                return
        # Admin commands (in pairs of 2 commands)
            await self.highrise.send_whisper(user.id, "👑 Yönetici Komutları:\n\n-skip - Şarkıyı atla\n-clear - Şarkı sırasını temizle\n-top <numara> - Şarkını sıranın en üstüne taşı")
            await self.highrise.send_whisper(user.id, "-remove <numara> - Sıradan şarkı kaldır\n-restart - Botu yeniden başlat")
            await self.highrise.send_whisper(user.id, "🚫 Engellenen Şarkı Komutları:\n\n-blocksong - Şu anda çalan şarkıyı engelle\n-blocklist - Engellenen şarkıları göster")
            await self.highrise.send_whisper(user.id, "-unblocksong <numara> - Engellenen şarkılar listesinden bir şarkının engelini kaldır")

            # User management commands (in pairs of 2 commands)
            await self.highrise.send_whisper(user.id, "👥 Kullanıcı Yönetimi:\n\n-addadmin @kullanıcı - Yönetici ekle\n-removeadmin @kullanıcı - Yönetici kaldır")
            await self.highrise.send_whisper(user.id, "-admins - Yönetici listesini göster\n-addvip @kullanıcı <seviye> - VIP ekle (1,2,3)")
            await self.highrise.send_whisper(user.id, "-removevip @kullanıcı - VIP kaldır")
            await self.highrise.send_whisper(user.id, "-history - Son çalınan şarkıları göster")

            # Blacklist management
            await self.highrise.send_whisper(user.id, "⛔ Kara Liste Yönetimi:\n\n-addblacklist @kullanıcı - Kara listeye ekle\n-rblacklist @kullanıcı - Kara listeden çıkar")
            await self.highrise.send_whisper(user.id, "-blacklist - Kara listeyi göster")
            await self.highrise.send_whisper(user.id, "🕺 Dans Komutları:\n\n-dance <emote adı> - Botun belirtilen dansı yapmasını sağla\n-dance - Botun rastgele dans etmesini sağla\n-stopdance - Botun dansını durdur\n-emotes - Tüm emote listesini göster")
            return

        elif message == "-lb":
            from user_stats import load_user_stats
            stats = load_user_stats()

            # Kullanıcıları şarkı isteklerine göre sırala
            sorted_users = sorted(stats.items(), key=lambda x: x[1]['song_requests'], reverse=True)

            # İlk 5 kullanıcıyı göster
            leaderboard = "🏆 Most Song Requests:\n\n"
            for i, (username, data) in enumerate(sorted_users[:5], 1):
                leaderboard += f"{i}. @{username}: {data['song_requests']} Song\n"

            # Komutu kullanan kişinin sıralamasını bul
            user_rank = next((i for i, (u, _) in enumerate(sorted_users, 1) if u == user.username), None)
            if user_rank:
                user_songs = stats[user.username]['song_requests']
                leaderboard += f"\nsıranız: # {user_rank} ({user_songs} şarkı)"
            else:
                leaderboard += f"\n👤 Henüz şarkı talep etmedin!"

            await self.highrise.send_whisper(user.id, leaderboard)
            return

        elif message == "-coinlb":
            from points_manager import load_points
            points_data = load_points()

            # Coin sıralamasında gözükmesini istemediğiniz kullanıcıları buraya ekleyin
            excluded_from_coinlb = [
                "AliMusic",
                "Mistava",
                "Ilikethewayyoukissme"
                # Bot kendisi
                # Buraya manuel olarak kullanıcı adları ekleyebilirsiniz:
                # "KullaniciAdi1",
                # "KullaniciAdi2",
            ]

            # Geçersiz verileri filtrele ve hariciler listesindeki kullanıcıları çıkar
            valid_users = {username: data for username, data in points_data.items() 
                          if (username != "check_all_users" and 
                              isinstance(data, dict) and 
                              "points" in data and 
                              username not in excluded_from_coinlb)}

            # Kullanıcıları puan değerlerine göre sırala
            sorted_users = sorted(valid_users.items(), key=lambda x: x[1]["points"], reverse=True)

            # İlk 5 kullanıcıyı göster
            leaderboard = "💰 En Çok Coin'e sahip olanlar:\n\n"
            for i, (username, data) in enumerate(sorted_users[:5], 1):
                leaderboard += f"{i}. @{username}: {data['points']} coin\n"

            # Komutu kullanan kişinin sıralamasını bul
            user_rank = next((i for i, (u, _) in enumerate(sorted_users, 1) if u == user.username), None)
            if user_rank:
                user_coins = points_data[user.username]['points']
                leaderboard += f"\n👤 Sıranız: #{user_rank} ({user_coins} coin)"
            else:
                leaderboard += f"\n👤 Henüz hiç coin kazanmadın!"

            await self.highrise.send_whisper(user.id, leaderboard)
            return

        elif message == "-myfav":
            from favorites_manager import get_user_favorites
            favorites = get_user_favorites(user.username)

            if not favorites:
                await self.highrise.send_whisper(user.id, "📝 Favori şarkı listen boş!")
                return

            # Önce başlık mesajı gönder
            await self.highrise.send_whisper(user.id, f"💖 Favori şarkıların ({len(favorites)}):")

            # Her favori şarkı için ayrı mesaj gönder
            for i, song in enumerate(favorites, 1):
                fav_message = f"{i}. {song['title']} (Added by: @{song['added_by']} )"
                await self.highrise.send_whisper(user.id, fav_message)
            return

        elif message.startswith("-favs"):
            target_username = message[6:].strip().replace('@', '')
            from favorites_manager import get_user_favorites
            favorites = get_user_favorites(target_username)

            if not favorites:
                await self.highrise.send_whisper(user.id, f"📝 @{target_username} kullanıcısının favori şarkı listesi boş!")
                return

            # Başlık mesajı
            await self.highrise.send_whisper(user.id, f"💖 @{target_username} kullanıcısının favori şarkıları ({len(favorites)}):")

            # Her bir şarkı için ayrı mesaj
            for i, song in enumerate(favorites, 1):
                fav_message = f"{i}. {song['title']} (Added by: @{song['added_by']} )"
                await self.highrise.send_whisper(user.id, fav_message)
            return

        elif message.startswith("-favdel"):
            try:
                indices = [int(x) for x in message[8:].strip().split()]
                if not indices:
                    await self.highrise.send_whisper(user.id, "❌ Silmek istediğin şarkıların sıra numaralarını gir lütfen!")
                    return

                from favorites_manager import remove_favorite
                if remove_favorite(user.username, indices):
                    await self.highrise.send_whisper(user.id, f"✅ Seçilen şarkılar favorilerinden kaldırıldı!")
                else:
                    await self.highrise.send_whisper(user.id, "❌ Şarkıları kaldırırken bir hata oluştu!")
            except ValueError:
                await self.highrise.send_whisper(user.id, "❌❌ Geçersiz sıra numarası!")
            return

        elif message.startswith("-skip"):
            if not self.is_admin(user.username):
                await self.highrise.send_whisper(user.id, f"❌ @{user.username} bu komutu kullanma iznin yok!")
                return
            await self.skip_song()
            return

        elif message.strip() == "-coin":
            from points_manager import get_user_points
            points = get_user_points(user.username)
            await self.highrise.send_whisper(user.id, f"💰 Coin Miktarınız {points}")
            return

        elif message.startswith("-g "):
            # Dedikasyon gönderme - 50 coin gerekiyor
            if not self.current_song:
                await self.highrise.send_whisper(user.id, "❌ Şu anda çalan bir şarkı yok!")
                return

            # Coin kontrolü
            from points_manager import get_user_points, use_points
            user_coins = get_user_points(user.username)
            required_coins = 50

            if user_coins < required_coins:
                await self.highrise.send_whisper(user.id, f"❌ Yeterli coin'in yok! Şarkı hediye etmek için {required_coins} coin gerekiyor. Coinlerin: {user_coins}")
                return

            target_username = message[3:].strip().replace('@', '')

            # Hedef kullanıcının odada olup olmadığını kontrol et
            room_users = (await self.highrise.get_room_users()).content
            user_exists = any(room_user.username == target_username for room_user, _ in room_users)

            if not user_exists:
                await self.highrise.send_whisper(user.id, f"❌ @{target_username} odada bulunamadı!")
                return

            # Kendine dedikasyon yapamaz
            if target_username == user.username:
                await self.highrise.chat(f"😅 @{user.username} o kadar yalnız ki, şarkıyı kendine hediye etmeye çalışıyor... Sana acıyoruz 💔")
                return

            # Dedikasyonu ayarla
            from dedication_manager import set_current_dedication
            result = set_current_dedication(user.username, target_username, self.current_song)

            if result.get("status", False):
                # Coin miktarını düş
                use_points(user.username, required_coins)

                # Dedikasyon yapan kişiye bildirme
                await self.highrise.send_whisper(user.id, f"✅ '{self.current_song}' şarkısını @{target_username} kullanıcısına başarıyla hediye ettin! (-{required_coins} coin)")

                # Hedef kullanıcıya bildirme
                target_id = next((room_user.id for room_user, _ in room_users if room_user.username == target_username), None)
                if target_id:
                    await self.highrise.send_whisper(target_id, f"🎁 @{user.username} sana '{self.current_song}' şarkısını hediye etti!")
            else:
                # Şarkı daha önce hediye edilmiş
                if "previous_from" in result and "previous_to" in result:
                    await self.highrise.send_whisper(user.id, f"❌ Bu şarkı zaten @{result['previous_from']} tarafından @{result['previous_to']} kullanıcısına hediye edilmiş!")
                else:
                    await self.highrise.send_whisper(user.id, "❌ Hediye gönderilirken bir hata oluştu!")
            return

        elif message.startswith("-p "):  # Add space after -p to ensure it's a song request
            song_name = message[len("-p "):].strip()
            await self.highrise.send_whisper(user.id, f"🔍 Şarkı aranıyor: {song_name}")

            try:
                # Asenkron şarkı araması
                song_info = await self.search_youtube(song_name)

                if song_info:
                    # Yasaklı şarkı kontrolü
                    from blocked_songs_manager import load_blocked_songs
                    blocked_songs = load_blocked_songs()
                    if song_info[1] in blocked_songs:
                        await self.highrise.send_whisper(user.id, "❌ Bu şarkı yasaklı listesinde olduğu için çalınamaz!")
                        return

                    # Şarkı süresi kontrolü (minimum 60 saniye, maksimum 7 dakika)
                    min_duration = 60  # 60 saniye
                    max_duration = 480  # 7 dakika
                    song_duration = song_info[2]  # duration (saniye cinsinden)

                    # Minimum süre kontrolü (admin dahil tüm kullanıcılar için)
                    if song_duration < min_duration:
                        await self.highrise.send_whisper(user.id, f"❌ Şarkı çok kısa! En az {min_duration} saniye uzunluğunda şarkılar çalabilirsiniz. Bu şarkı {song_duration} saniye uzunluğunda.")
                        return

                    # Admin kullanıcılar için süre limiti yok, diğer kullanıcılar için 7 dakika limit
                    if not self.is_admin(user.username) and song_duration > max_duration:
                        minutes = max_duration // 60
                        seconds = max_duration % 60
                        song_minutes = song_duration // 60
                        song_seconds = song_duration % 60
                        await self.highrise.send_whisper(user.id, f"❌ Şarkı çok uzun! En fazla {minutes}:{seconds:02d} dakika uzunluğunda şarkı çalabilirsin. Bu şarkı ise {song_minutes}:{song_seconds:02d} dakika.")
                        return

                    if self.is_playing:
                        # Check if song is already in queue
                        duplicate_song = next((song for song in self.queue if song[1].lower() == song_info[1].lower()), None)
                        if duplicate_song:
                            duplicate_user = duplicate_song[3]
                            await self.highrise.send_whisper(user.id, f"❌ Bu şarkı zaten @{duplicate_user} tarafından kuyruğa eklendi!")
                            return

                        song_with_user = (*song_info, user.username)  # URL, title, duration, username
                        self.queue.append(song_with_user)
                        from queue_manager import save_queue
                        save_queue(self.queue)
                        queue_position = len(self.queue)

                        # VIP emoji gösterimi
                        vip_level = self.get_user_vip_level(user.username)
                        admin_emoji = "👑 " if self.is_admin(user.username) else ""
                        vip_emoji = ""
                        if vip_level > 0 and not self.is_admin(user.username):
                            from vip_manager import get_vip_emoji
                            vip_emoji = f"{get_vip_emoji(vip_level)} "

                        await self.highrise.chat(f"🎵 @{user.username} {admin_emoji}{vip_emoji} tarafından kuyruğa eklendi (Sıra #{queue_position}):\n\n{song_info[1]}")
                    else:
                        song_with_user = (*song_info, user.username)
                        self.queue.append(song_with_user)
                        await self.play_song_with_info(song_info[0], song_info[1], song_info[2], user.username)
            except Exception as e:
                await self.highrise.chat("❌ Şarkı bulunamadı veya bir sorun var")
                print(f"Error: {e}")

        elif message == "-myg":
            from dedication_manager import get_user_dedications
            dedications = get_user_dedications(user.username)

            if not dedications:
                await self.highrise.send_whisper(user.id, "📝 Henüz sana hediye edilen bir şarkı yok!")
                return

            await self.highrise.send_whisper(user.id, f"🎁 Sana hediye edilen şarkılar({len(dedications)}):")
            for i, dedication in enumerate(dedications, 1):
                await self.highrise.send_whisper(user.id, f"{i}. {dedication['song']}\n👤 Hediye eden: @{dedication['from']}")
            return

        elif message == "-daily":
            # VIP seviyesi 2 ve 3 için özel bonus
            vip_level = self.get_user_vip_level(user.username)

            from points_manager import give_daily_bonus
            result, message_text = await give_daily_bonus(user.username, self)

            if result and vip_level >= 2:
                # VIP'lere ek bonus ver
                from points_manager import add_points
                bonus_amount = 50 if vip_level == 2 else 100  # Kademe 2: +50, Kademe 3: +100
                add_points(user.username, bonus_amount)

                # VIP'lere top komutu hakkı ver
                from cooldown_manager import load_cooldowns, save_cooldowns
                cooldowns = load_cooldowns()
                today = time.strftime("%Y-%m-%d")

                if user.username not in cooldowns:
                    cooldowns[user.username] = {}

                top_usage_key = f"top_usage_{today}"
                current_usage = cooldowns[user.username].get(top_usage_key, 0)

                # Günlük top hakkını ver (sadece Kademe 2 ve 3 için)
                if vip_level >= 2:
                    daily_limit = 3 if vip_level == 3 else 2  # Kademe 3: 3 hak, Kademe 2: 2 hak
                    top_bonus = daily_limit - current_usage if current_usage < daily_limit else 0

                    if top_bonus > 0:
                        # Top hakkını sıfırla (yani yeniden kullanabilir hale getir)
                        from points_manager import reset_top_usage
                        reset_top_usage(user.username)
                else:
                    top_bonus = 0

                from vip_manager import get_vip_emoji
                emoji = get_vip_emoji(vip_level)
                message_text += f"\n{emoji} VIP Bonusu: +{bonus_amount} coin!"
                if vip_level >= 2 and top_bonus > 0:
                    daily_limit = 3 if vip_level == 3 else 2
                    message_text += f"\n⬆️ Günlük {daily_limit} top komutu hakkı yenilendi!"

            if result:
                await self.highrise.send_whisper(user.id, f"🎁 {message_text}")
            else:
                await self.highrise.send_whisper(user.id, f"❌ {message_text}")
            return

        elif message.startswith("-up"):
            from points_manager import use_points, get_user_points

            # Kullanıcının şarkılarını bul
            user_songs = [(i, song) for i, song in enumerate(self.queue) if song[3] == user.username]

            if not user_songs:
                await self.highrise.send_whisper(user.id, "❌ Sırada bir şarkınız yok!")
                return

            # Tek şarkısı varsa ilk şarkıyı al, birden fazla şarkı varsa uyarı ver
            if len(user_songs) == 1:
                index, song = user_songs[0]
            elif message.strip() == "-up":
                await self.highrise.send_whisper(user.id, f"❌ Birden fazla şarkınız var! Doğru kullanım: -up <şarkı numarası>")
                await self.highrise.send_whisper(user.id, "🎵 Şarkılarınız:")
                for i, (_, song) in enumerate(user_songs):
                    await self.highrise.send_whisper(user.id, f"{i+1}. {song[1]}")
                return
            else:
                try:
                    # -up komutundan sonraki sayıyı al
                    song_number = int(message.split()[1]) - 1
                    if 0 <= song_number < len(user_songs):
                        index, song = user_songs[song_number]
                    else:
                        await self.highrise.send_whisper(user.id, f"❌ Geçersiz şarkı numarası!")
                        await self.highrise.send_whisper(user.id, "🎵 Şarkılarınız:")
                        for i, (_, song) in enumerate(user_songs):
                            await self.highrise.send_whisper(user.id, f"{i+1}. {song[1]}")
                        return
                except (IndexError, ValueError):
                    await self.highrise.send_whisper(user.id, f"❌ Lütfen bir şarkı numarası girin:")
                    await self.highrise.send_whisper(user.id, "🎵 Şarkılarınız:")
                    for i, (_, song) in enumerate(user_songs):
                        await self.highrise.send_whisper(user.id, f"{i+1}. {song[1]}")
                    return

            if index == 0:
                await self.highrise.send_whisper(user.id, "❌ Şarkınız zaten sıranın en üstünde!")
                return

            if get_user_points(user.username) >= 100:
                if use_points(user.username, 100):
                    # Şarkıyı bir üst sıraya taşı
                    self.queue[index], self.queue[index-1] = self.queue[index-1], self.queue[index]
                    from queue_manager import save_queue
                    save_queue(self.queue)
                    await self.highrise.send_whisper(user.id, f"⬆️ '{song[1]}' bir sıra yukarı taşındı! (Yeni konum: {index})")
                else:
                    await self.highrise.send_whisper(user.id, "❌ Bir hata oluştu!")
            else:
                await self.highrise.send_whisper(user.id, "❌ Yetersiz puan! (Gerekli: 100)")

        elif message.startswith("-dance") and self.is_admin(user.username):
            from emotes_data import paid_emotes

            args = message.split()
            if len(args) > 1:
                # Belirli bir emote için
                emote_name = " ".join(args[1:])
                emote_data = next((data for name, data in paid_emotes.items() if name.lower() == emote_name.lower()), None)

                if emote_data:
                    # Mevcut dans döngüsünü durdur ve yeniden başlat
                    self.dance_running = False
                    await asyncio.sleep(0.5)  # Kısa bir bekleme süresi
                    self.current_emote = emote_data["value"]
                    from emotes_data import save_current_emote
                    save_current_emote(self.current_emote)
                    self.dance_running = True
                    await self.highrise.chat(f"🕺 {emote_name} dans baslıyorrrrr")

                else:
                    await self.highrise.chat("❌ Emote bulunamadı")
            else:
                # Rastgele emote için
                self.current_emote = None
                if not self.dance_running:
                    self.dance_running = True
                    await self.highrise.chat("🕺 rastgele dans baslıyorrrrr")
                else:
                    await self.highrise.chat("🕺 zaten dans ediyorum")

        elif message == "-stopdance" and self.is_admin(user.username):
            if self.dance_running:
                self.dance_running = False
                self.current_emote = None
                from emotes_data import save_current_emote
                save_current_emote(None)
                await self.highrise.chat("🕺 Dans bitti")
            else:
                await self.highrise.chat("🕺 Şuanda dans etmiyorum.")

        elif message == "-emotes" and self.is_admin(user.username):
            from emotes_data import paid_emotes
            emote_list = list(paid_emotes.keys())
            # Her 10 emote'u bir mesajda gönder
            for i in range(0, len(emote_list), 10):
                chunk = emote_list[i:i+10]
                await self.highrise.send_whisper(user.id, "🎭 " + ", ".join(chunk))



        elif message.startswith("-rate "):
            if not self.current_song:
                await self.highrise.send_whisper(user.id, "❌ Şu anda çalan bir şarkı yok!")
                return

            try:
                rating = int(message[6:].strip())
                if rating < 1 or rating > 10:
                    await self.highrise.send_whisper(user.id, "❌ Puan 1 ile 10 arasında olmalıdır!")
                    return

                from rating_manager import add_rating
                success, message_text = add_rating(self.current_song, user.username, rating)

                if success:
                    await self.highrise.send_whisper(user.id, f"⭐ {message_text}")
                else:
                    await self.highrise.send_whisper(user.id, f"❌ {message_text}")

            except ValueError:
                await self.highrise.send_whisper(user.id, "❌ Lütfen geçerli bir puan girin (1-10)")
            return

        elif message == "-ratelb":
            from rating_manager import get_top_rated_songs
            top_songs = get_top_rated_songs(5)

            if not top_songs:
                await self.highrise.send_whisper(user.id, "📝 Henüz puanlanmış şarkı yok!")
                return

            await self.highrise.send_whisper(user.id, "🏆 En Yüksek Puanlı 5 Şarkı:")
            for i, (song_title, song_data) in enumerate(top_songs, 1):
                avg_rating = song_data["average_rating"]
                rating_count = song_data["rating_count"]
                await self.highrise.send_whisper(user.id, f"{i}. {song_title}\n⭐ {avg_rating:.1f}/10 ({rating_count} oy)")
            return

        elif message == "-shop":
            # Shop komutunu kullanabilmek için DM uyarısı
            await self.highrise.send_whisper(user.id, "💡 Shop menüsünü kullanmak için lütfen bana DM (özel mesaj) atın ve '-shop' yazın!")
            return



    async def play_song_with_info(self, youtube_url: str, title: str, duration: int, username: str = None) -> None:
        try:
            minutes = duration // 60
            seconds = duration % 60

            # Eğer şarkı zaten çalıyorsa yeni bir başlatma
            if self.is_playing and hasattr(self, 'current_thread') and self.current_thread and self.current_thread.is_alive():
                return

            # Şarkıyı queue'dan çıkar (sadece queue'nun başında olan şarkı çalınıyorsa)
            if self.queue and self.queue[0][1] == title and self.queue[0][3] == username:
                removed_song = self.queue.pop(0)
                from queue_manager import save_queue
                save_queue(self.queue)

            # Her yeni şarkıda oyları sıfırla
            if hasattr(self, 'skip_votes'):
                self.skip_votes.clear()

            # Save to history
            from history_manager import save_history
            save_history({
                "title": title,
                "duration": duration,
                "username": username,
                "timestamp": time.time()
            })

            # Kullanıcı bilgisini ayarla
            self.current_song = title
            self.current_song_username = username
            self.is_playing = True
            self.should_stop = False

            # VIP emoji gösterimi
            vip_level = self.get_user_vip_level(username)
            admin_emoji = "👑 " if self.is_admin(username) else ""
            vip_emoji = ""
            if vip_level > 0 and not self.is_admin(username):
                from vip_manager import get_vip_emoji
                vip_emoji = f"{get_vip_emoji(vip_level)} "

            # Çalınacak şarkıyı bildir
            await self.highrise.chat(f"🎵 Şu anda çalıyor: {title} 🎵 ▷ •ı||ıı|ıı|ı||ı|ıı||ı• {minutes}:{seconds:02d} (Talep eden: @{username} {admin_emoji}{vip_emoji})")

            # Mevcut dedikasyonu temizle
            from dedication_manager import clear_current_dedication
            clear_current_dedication()

            def stream_thread():
                from user_stats import increment_song_request
                increment_song_request(username)
                self.stream_to_zeno(youtube_url)

            self.current_thread = Thread(target=stream_thread)
            self.current_thread.start()

        except Exception as e:
            await self.highrise.chat("❌ Hata: Şarkı bulunamadı veya çalınamadı")
            print(f"Error: {e}")
            self.is_playing = False
            self.current_song = None
            self.current_song_username = None

    async def skip_song(self) -> None:
        if not self.is_playing:
            await self.highrise.chat("❌ Şu anda çalan bir şarkı yok")
            return

        if not self.queue:
            await self.highrise.chat("❌ Atlanacak bir şarkı sırada yok")
            return

        # Clear skip votes for the next song
        if hasattr(self, 'skip_votes'):
            self.skip_votes.clear()

        await self.highrise.chat(f"⏭️ Şarkı atlanıyor...")

        # Mevcut işlemi durdur
        self.should_stop = True

        # FFmpeg işlemini sonlandır
        if hasattr(self, 'process'):
            try:
                self.process.terminate()
                self.process.kill()
            except:
                pass

        # Thread'i bekle
        if self.current_thread and self.current_thread.is_alive():
            try:
                self.current_thread.join(timeout=0.1)
            except:
                pass

        # Durumu resetle
        self.is_playing = False
        self.current_song = None
        self.current_song_username = None
        self.current_thread = None

        # Sıradaki şarkıyı çal
        if self.queue:
            next_song_info = self.queue[0]
            await self.play_song_with_info(*next_song_info)
        else:
            await self.highrise.chat("📝 Sırada başka şarkı yok")

    async def search_youtube(self, query: str) -> tuple:
        ydl_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'force_generic_extractor': False,
            'nocheckcertificate': True,
            'ignoreerrors': False,
            'logtostderr': False,
            'cookiefile': os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cookies.txt'),
            'default_search': 'ytsearch'
        }

        def _search():
            with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                info_dict = ydl.extract_info(f"ytsearch:{query}", download=False)
                video_info = info_dict['entries'][0]
                url = video_info.get('url', None)
                if not url:
                    formats = video_info.get('formats', [])
                    url = formats[-1]['url'] if formats else video_info['webpage_url']
                return (url, video_info['title'], video_info['duration'])

        try:
            # ThreadPoolExecutor kullanarak arama işlemini arka planda yap
            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor() as pool:
                result = await loop.run_in_executor(pool, _search)
                return result
        except Exception as e:
            print(f"YouTube search error: {str(e)}")
            raise

    def stream_to_zeno(self, youtube_url: str) -> None:
        max_retries = 3
        retry_count = 0

        while retry_count < max_retries and not self.should_stop:
            try:
                start_time = time.time()
                current_duration = None
                current_username = None
                current_title = None

                # Her yeni şarkıda oyları sıfırla
                if hasattr(self, 'skip_votes'):
                    self.skip_votes.clear()

                # Çalan şarkının bilgilerini al
                if self.queue:
                    old_url, current_title, current_duration, current_username = self.queue[0]
                    self.current_song_username = current_username

                self.process = (
                    ffmpeg
                    .input(youtube_url, re=None, timeout=10000000)
                    .output(
                        'icecast://source:4jQtitpx@link.zeno.fm:80/xtxnjta7v1kuv',
                        acodec='libmp3lame',
                        ar='44100',
                        ac='2',
                        ab='128k',
                        content_type='audio/mpeg',
                        f='mp3',
                        ice_name='Highrise Radio',
                        ice_description='Live Radio Stream'
                    )
                    .overwrite_output()
                    .run_async(cmd=['ffmpeg', '-loglevel', 'panic'])
                )

                # Şarkı çalmaya başladıktan sonra queue'dan çıkar
                if self.queue:
                    removed_song = self.queue.pop(0)
                    from queue_manager import save_queue
                    save_queue(self.queue)

                # FFmpeg işleminin tamamen bitmesini bekle
                while self.process.poll() is None and not self.should_stop:
                    time.sleep(0.1)

                # Process tamamlandıktan sonra ek kontrol
                if not self.should_stop:
                    time.sleep(1)  # Şarkının tamamen bittiğinden emin olmak için 1 saniye bekle

                if not self.should_stop and self.queue:
                    next_song = self.queue[0]
                    youtube_url, title, duration, username = next_song  # url, title, duration, username
                    self.current_song = title
                    self.current_song_username = username
                    self.is_playing = True

                    # Sonraki şarkı mesajı gönder
                    Thread(target=lambda: asyncio.run(self.send_now_playing_message(title, duration))).start()

                    # Sonraki şarkıyı çal
                    self.stream_to_zeno(youtube_url)
                else:
                    self.is_playing = False
                    self.current_song = None
                    self.current_song_username = None
                break

            except ffmpeg.Error as e:
                print(f"FFmpeg error occurred: {e.stderr.decode() if e.stderr else 'Unknown error'}")
                retry_count += 1
                if retry_count < max_retries:
                    print(f"Retrying... Attempt {retry_count + 1}/{max_retries}")
                    continue
            except Exception as e:
                print(f"Unexpected error: {str(e)}")
                retry_count += 1
                if retry_count < max_retries:
                    print(f"Retrying... Attempt {retry_count + 1}/{max_retries}")
                    continue
            break

    async def handle_next_song(self):
        """Sıradaki şarkıya güvenli bir şekilde geçer"""
        try:
            # Mevcut durumu temizle
            self.is_playing = False
            self.current_song = None
            self.current_song_username = None

            # Skip votes'u temizle
            if hasattr(self, 'skip_votes'):
                self.skip_votes.clear()

            if self.queue:
                next_song_info = self.queue[0]  # İlk şarkıyı al
                await self.play_song_with_info(*next_song_info)
            else:
                await self.highrise.chat("📝 Sırada başka şarkı yok")
        except Exception as e:
            print(f"Error in handle_next_song: {e}")
            self.is_playing = False
            self.current_song = None
            self.current_song_username = None

    async def announce_next_song(self):
        if self.queue:
            next_song = self.queue[0]
            _, title, _, username = next_song  # url, title, duration, username
            await self.highrise.chat(f"🎵 Sıradaki şarkı: {title}\n👤 Added by: @{username}")

    async def on_message(self, user_id: str, conversation_id: str, is_new_conversation: bool) -> None:
        try:
            response = await self.highrise.get_messages(conversation_id)
            if isinstance(response.messages, list) and len(response.messages) > 0:
                message = response.messages[0].content

                # Get username from user_id
                room_users_response = await self.highrise.get_room_users()
                username = None
                if hasattr(room_users_response, 'content'):
                    room_users = room_users_response.content
                    for user, _ in room_users:
                        if user.id == user_id:
                            username = user.username
                            break

                if not username:
                    await self.highrise.send_message(conversation_id, "❌ Shop menüsünü kullanabilmek için lütfen önce odaya gelip DM atın!\n\n🔗 Oda linki: https://high.rs/room?id=68868575b8a463ac41b6eaba&invite_id=68875cd71991d248682b049b")
                    return

                # Shop menü durumunu kontrol et
                if hasattr(self, 'user_shop_state') and user_id in self.user_shop_state:
                    shop_state = self.user_shop_state[user_id]

                    if shop_state.get('in_shop', False):
                        if shop_state.get('menu') == 'main':
                            # Ana menüden seçim
                            if message == "1":
                                # Coin menüsü
                                from wallet_manager import get_gold
                                from points_manager import get_user_points

                                gold_balance = get_gold(username)
                                coin_balance = get_user_points(username)

                                coin_menu = (
                                    f"💰 COIN MENÜSÜ 💰\n\n"
                                    f"💎 Gold Bakiyeniz: {gold_balance}\n"
                                    f"💰 Coin Bakiyeniz: {coin_balance}\n\n"
                                    f"1️⃣ 100 Coin = 10 Gold\n"
                                    f"2️⃣ 200 Coin = 20 Gold\n"
                                    f"3️⃣ 300 Coin = 30 Gold\n"
                                    f"4️⃣ 400 Coin = 40 Gold\n"
                                    f"5️⃣ 500 Coin = 50 Gold\n"
                                    f"6️⃣ 1000 Coin = 90 Gold\n\n"
                                    f"0️⃣ Ana Menüye Dön\n"
                                    f"❌ Çıkış\n\n"
                                    f"Seçim yapmak için sayı yazın"
                                )

                                await self.highrise.send_message(conversation_id, coin_menu)
                                self.user_shop_state[user_id]['menu'] = 'coin'
                                return

                            elif message == "2":
                                # VIP Menüsü
                                from wallet_manager import get_gold
                                from temp_vip_manager import get_temp_vip_info

                                gold_balance = get_gold(username)
                                temp_vip_info = get_temp_vip_info(username)

                                vip_status = ""
                                if temp_vip_info:
                                    vip_status = f"\n🌟 Mevcut VIP: Kademe {temp_vip_info['level']} ({temp_vip_info['days_left']} gün kaldı)"

                                vip_menu = (
                                    f"✨ VIP MENÜSÜ ✨\n\n"
                                    f"💎 Gold Bakiyeniz: {gold_balance}{vip_status}\n\n"
                                    f"1️⃣ Kademe 1 VIP ⭐ = 200 Gold (30 gün)\n"
                                    f"   • Sıraya 2 şarkı ekleme\n\n"
                                    f"2️⃣ Kademe 2 VIP 🌟 = 350 Gold (30 gün)\n"
                                    f"   • Sıraya 2 şarkı ekleme\n"
                                    f"   • Günlük 2 -top komutu hakkı (şarkını sıranın başına taşı)\n"
                                    f"   • Günlük bonus +50 coin\n\n"
                                    f"3️⃣ Kademe 3 VIP 💎 = 500 Gold (30 gün)\n"
                                    f"   • Sıraya 2 şarkı ekleme\n"
                                    f"   • Günlük 3 -top komutu hakkı (şarkını sıranın başına taşı)\n"
                                    f"   • Günlük bonus +100 coin\n\n"
                                    f"0️⃣ Ana Menüye Dön\n"
                                    f"❌ Çıkış\n\n"
                                    f"Seçim yapmak için sayı yazın"
                                )

                                await self.highrise.send_message(conversation_id, vip_menu)
                                self.user_shop_state[user_id]['menu'] = 'vip'
                                return

                            elif message in ["3", "4"]:
                                await self.highrise.send_message(conversation_id, "🚧 Bu menü henüz mevcut değil. Yakında eklenecek!")
                                return

                            elif message.lower() in ["❌", "exit", "çıkış"]:
                                del self.user_shop_state[user_id]
                                await self.highrise.send_message(conversation_id, "👋 Shop'tan çıkıldı!")
                                return

                        elif shop_state.get('menu') == 'coin':
                            # Coin menüsünden seçim
                            coin_packages = {
                                "1": {"coins": 100, "gold": 10},
                                "2": {"coins": 200, "gold": 20},
                                "3": {"coins": 300, "gold": 30},
                                "4": {"coins": 400, "gold": 40},
                                "5": {"coins": 500, "gold": 50},
                                "6": {"coins": 1000, "gold": 90}
                            }

                            if message in coin_packages:
                                package = coin_packages[message]
                                coins_to_buy = package["coins"]
                                gold_cost = package["gold"]

                                from wallet_manager import get_gold, use_gold
                                from points_manager import get_user_points, add_points

                                # İşlem sırasında iki kez gold kontrolü yap
                                current_gold = get_gold(username)

                                if current_gold >= gold_cost:
                                    # Gold'u düş
                                    if use_gold(username, gold_cost):
                                        # Coin ekleme işlemi
                                        if add_points(username, coins_to_buy):
                                            new_gold = get_gold(username)
                                            new_coins = get_user_points(username)

                                            success_msg = (
                                                f"✅ Satın alma başarılı!\n\n"
                                                f"🛒 {coins_to_buy} Coin aldınız\n"
                                                f"💎 {gold_cost} Gold ödendi\n\n"
                                                f"💎 Yeni Gold Bakiyeniz: {new_gold}\n"
                                                f"💰 Yeni Coin Bakiyeniz: {new_coins}"
                                            )
                                            await self.highrise.send_message(conversation_id, success_msg)

                                            # Satın alımdan sonra otomatik çıkış
                                            del self.user_shop_state[user_id]
                                            await self.highrise.send_message(conversation_id, "🛒 Shop'tan otomatik olarak çıkıldı! Yeniden -shop yazarak menüye erişebilirsiniz.")
                                        else:
                                            # Coin ekleme başarısızsa gold'u geri ver
                                            from wallet_manager import add_gold
                                            add_gold(username, gold_cost)
                                            await self.highrise.send_message(conversation_id, "❌ Coin ekleme sırasında hata oluştu! Gold iadesi yapıldı.")
                                    else:
                                        await self.highrise.send_message(conversation_id, "❌ Gold düşme işlemi başarısız oldu!")
                                else:
                                    await self.highrise.send_message(conversation_id, f"❌ Yetersiz Gold! Gerekli: {gold_cost} Gold, Mevcut: {current_gold} Gold")
                                return

                            elif message == "0":
                                # Ana menüye dön
                                from wallet_manager import get_gold
                                from points_manager import get_user_points

                                gold_balance = get_gold(username)
                                coin_balance = get_user_points(username)

                                shop_menu = (
                                    f"🏪 SHOP MENÜSÜ 🏪\n\n"
                                    f"💰 Coin Bakiyeniz: {coin_balance}\n"
                                    f"💎 Gold Bakiyeniz: {gold_balance}\n\n"
                                    f"1️⃣ Coin Menüsü\n"
                                    f"2️⃣ VIP Menüsü ✨\n"
                                    f"3️⃣ Yakında...\n"
                                    f"4️⃣ Yakında...\n\n"
                                    f"Seçim yapmak için sayı yazın (1-4)"
                                )

                                await self.highrise.send_message(conversation_id, shop_menu)
                                self.user_shop_state[user_id]['menu'] = 'main'
                                return

                            elif message.lower() in ["❌", "exit", "çıkış"]:
                                del self.user_shop_state[user_id]
                                await self.highrise.send_message(conversation_id, "👋 Shop'tan çıkıldı!")
                                return

                        elif shop_state.get('menu') == 'vip':
                            # VIP menüsünden seçim
                            vip_packages = {
                                "1": {"level": 1, "gold": 200, "days": 30},
                                "2": {"level": 2, "gold": 350, "days": 30},
                                "3": {"level": 3, "gold": 500, "days": 30}
                            }

                            if message in vip_packages:
                                package = vip_packages[message]
                                vip_level = package["level"]
                                gold_cost = package["gold"]
                                vip_days = package["days"]

                                # Mevcut VIP kontrolü
                                from temp_vip_manager import get_temp_vip_info
                                existing_vip = get_temp_vip_info(username)

                                if existing_vip:
                                    await self.highrise.send_message(conversation_id, f"❌ Zaten aktif VIP'iniz var!\n\n⭐ Mevcut VIP Kademe: {existing_vip['level']}\n📅 Kalan Süre: {existing_vip['days_left']} gün\n🗓️ Bitiş Tarihi: {existing_vip['expiry_date']}\n\nMevcut VIP'iniz bittikten sonra yeni VIP alabilirsiniz.")
                                    return

                                from wallet_manager import get_gold, use_gold
                                from temp_vip_manager import add_temp_vip

                                current_gold = get_gold(username)

                                if current_gold >= gold_cost:
                                    # Gold'u düş ve VIP ekle
                                    if use_gold(username, gold_cost):
                                        add_temp_vip(username, vip_level, vip_days)

                                        new_gold = get_gold(username)
                                        from temp_vip_manager import get_temp_vip_info
                                        temp_vip_info = get_temp_vip_info(username)
                                        vip_status = f"Kademe {temp_vip_info['level']} ({temp_vip_info['days_left']} gün kaldı)" if temp_vip_info else "Yok"

                                        success_msg = (
                                            f"✅ Satın alma başarılı!\n\n"
                                            f"✨ VIP Kademe {vip_level} alındı ({vip_days} gün)\n"
                                            f"💎 {gold_cost} Gold ödendi\n\n"
                                            f"💎 Yeni Gold Bakiyeniz: {new_gold}\n"
                                            f"🌟 VIP Statünüz: {vip_status}"
                                        )
                                        await self.highrise.send_message(conversation_id, success_msg)

                                        # Satın alımdan sonra otomatik çıkış
                                        del self.user_shop_state[user_id]
                                        await self.highrise.send_message(conversation_id, "🛒 Shop'tan otomatik olarak çıkıldı! Yeniden -shop yazarak menüye erişebilirsiniz.")
                                    else:
                                        await self.highrise.send_message(conversation_id, "❌ Satın alma sırasında bir hata oluştu!")
                                else:
                                    await self.highrise.send_message(conversation_id, f"❌ Yetersiz Gold! Gerekli: {gold_cost} Gold, Mevcut: {current_gold} Gold")
                                return

                            elif message == "0":
                                # Ana menüye dön
                                from wallet_manager import get_gold
                                from points_manager import get_user_points

                                gold_balance = get_gold(username)
                                coin_balance = get_user_points(username)

                                shop_menu = (
                                    f"🏪 SHOP MENÜSÜ 🏪\n\n"
                                    f"💰 Coin Bakiyeniz: {coin_balance}\n"
                                    f"💎 Gold Bakiyeniz: {gold_balance}\n\n"
                                    f"1️⃣ Coin Menüsü\n"
                                    f"2️⃣ VIP Menüsü ✨\n"
                                    f"3️⃣ Yakında...\n"
                                    f"4️⃣ Yakında...\n\n"
                                    f"Seçim yapmak için sayı yazın (1-4)"
                                )

                                await self.highrise.send_message(conversation_id, shop_menu)
                                self.user_shop_state[user_id]['menu'] = 'main'
                                return

                            elif message.lower() in ["❌", "exit", "çıkış"]:
                                del self.user_shop_state[user_id]
                                await self.highrise.send_message(conversation_id, "👋 Shop'tan çıkıldı!")
                                return

                        # Geçersiz seçim
                        await self.highrise.send_message(conversation_id, "❌ Geçersiz seçim! Lütfen menüdeki sayıları kullanın.")
                        return

                # Shop dışındaki normal komutlar
                if message == "-shop":
                    # Shop ana menüsü
                    from wallet_manager import get_gold
                    from points_manager import get_user_points

                    gold_balance = get_gold(username)
                    coin_balance = get_user_points(username)

                    shop_menu = (
                        f"🏪 SHOP MENÜSÜ 🏪\n\n"
                        f"💰 Coin Bakiyeniz: {coin_balance}\n"
                        f"💎 Gold Bakiyeniz: {gold_balance}\n\n"
                        f"1️⃣ Coin Menüsü\n"
                        f"2️⃣ VIP Menüsü ✨\n"
                        f"3️⃣ Yakında...\n"
                        f"4️⃣ Yakında...\n\n"
                        f"Seçim yapmak için sayı yazın (1-4)"
                    )

                    await self.highrise.send_message(conversation_id, shop_menu)

                    # Kullanıcının shop menüsünde olduğunu işaretle
                    if not hasattr(self, 'user_shop_state'):
                        self.user_shop_state = {}
                    self.user_shop_state[user_id] = {'in_shop': True, 'menu': 'main'}
                    return

                elif message == "-bal":
                    from wallet_manager import get_gold
                    gold_balance = get_gold(username)
                    await self.highrise.send_message(conversation_id, f"💰 Gold Bakiyeniz: {gold_balance}")
                    return

        except Exception as e:
            print(f"Error in on_message: {e}")

    async def on_tip(self, sender: User, receiver: User, tip) -> None:
        try:
            from wallet_manager import add_gold, get_gold

            # Sadece bota atılan goldları işle
            if receiver.id == self.user_id:
                if hasattr(tip, 'type'):
                    if tip.type == "earned_gold" or tip.type == "gold":
                        amount = tip.amount if hasattr(tip, 'amount') else 1
                        if add_gold(sender.username, amount):
                            new_balance = get_gold(sender.username)
                            await self.highrise.send_whisper(sender.id, f"💰 Wallet'ınıza {amount} gold eklendi!\nToplam Gold: {new_balance}")
                            print(f"DEBUG: Added {amount} gold to {sender.username}")
                        else:
                            print(f"Error adding gold for {sender.username}")
                            await self.highrise.send_whisper(sender.id, "❌ Gold eklenirken bir hata oluştu!")
        except Exception as e:
            print(f"Error in on_tip: {e}")

    async def send_now_playing_message(self, title: str, duration: int) -> None:
        try:
            minutes = duration // 60
            seconds = duration % 60

            # Kullanıcı adını self.current_song_username'den al
            username_display = self.current_song_username if hasattr(self, 'current_song_username') and self.current_song_username else 'Unknown'

            # VIP emoji gösterimi
            vip_level = self.get_user_vip_level(username_display)
            admin_emoji = "👑 " if self.is_admin(username_display) else ""
            vip_emoji = ""
            if vip_level > 0 and not self.is_admin(username_display):
                from vip_manager import get_vip_emoji
                vip_emoji = f"{get_vip_emoji(vip_level)} "


            await self.highrise.chat(f"🎵 Şu anda çalıyor: {title}\n🎵 ▷ •ı||ıı|ıı|ı||ı|ıı||ı• {minutes}:{seconds:02d}\n(Talep eden: @{username_display} {admin_emoji}{vip_emoji})")
        except Exception as e:
            print(f"Error sending message: {e}")

class RunBot():
    room_id = "6828f1aa281d704355d5c6f8"
    bot_token = "0b89956c18f0384e1c1d7d95b0efb2fc4a25b75b139fc7af9385af9ea94d470e"
    bot_file = "main"
    bot_class = "MyBot"

    def __init__(self) -> None:
        self.definitions = [
            BotDefinition(
                getattr(import_module(self.bot_file), self.bot_class)(),
                self.room_id, self.bot_token)
        ]

    def run_loop(self) -> None:
        while True:
            try:
                arun(main(self.definitions))
            except Exception as e:
                import traceback
                print("Caught an exception:")
                traceback.print_exc()
                time.sleep(1)
                continue

if __name__ == "__main__":
    WebServer().keep_alive()
    RunBot().run_loop()
from temp_vip_manager import *