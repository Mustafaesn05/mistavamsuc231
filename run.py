import ffmpeg
import yt_dlp as youtube_dl
from highrise import BaseBot, SessionMetadata
from highrise.__main__ import *
from threading import Thread
import time
import asyncio
import threading
from flask import Flask
import os

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
        self.queue = []  # Queue system
        self.current_song = None
        self.is_playing = False
        self.current_thread = None
        self.should_stop = False

    async def on_start(self, session_metadata: SessionMetadata) -> None:
        print(session_metadata)

    async def on_chat(self, session_metadata: SessionMetadata, message: str) -> None:
        if message in ["!queue", "!q"]:
            if not self.queue and not self.current_song:
                await self.highrise.chat("📝 Sırada şarkı yok")
                return

            response = "🎵 Sıradaki şarkılar:"
            for i, (_, title, duration) in enumerate(self.queue, 1):
                minutes = duration // 60
                seconds = duration % 60
                response += f"\n{i}. {title} [{minutes}:{seconds:02d}]"
            await self.highrise.chat(response)
            return

        elif message == "!n":
            if self.current_song:
                await self.highrise.chat(f"🎵 Şu an çalıyor: {self.current_song}")
            else:
                await self.highrise.chat("❌ Şu anda çalan şarkı yok")
            return

        elif message == "!m":
            if self.queue:
                _, title, duration = self.queue[-1]
                minutes = duration // 60
                seconds = duration % 60
                await self.highrise.chat(f"🎵 Son eklediğiniz şarkı: {title} [{minutes}:{seconds:02d}]")
            else:
                await self.highrise.chat("❌ Sırada şarkı yok")
            return

        elif message == "!clear":
            self.queue.clear()
            await self.highrise.chat("🗑️ Sıra temizlendi")
            return

        elif message.startswith("!remove "):
            try:
                index = int(message[8:].strip()) - 1
                if 0 <= index < len(self.queue):
                    removed_song = self.queue.pop(index)
                    await self.highrise.chat(f"❌ Sıradan çıkarıldı: {removed_song[1]}")
                else:
                    await self.highrise.chat("❌ Geçersiz sıra numarası")
            except ValueError:
                await self.highrise.chat("❌ Lütfen geçerli bir numara girin")
            return

        elif message.startswith("!play"):
            song_name = message[len("!play "):].strip()

            # Start searching for the song
            await self.highrise.chat(f"🔍 Aranıyor: {song_name}")
            try:
                song_info = await self.search_youtube(song_name)
                if self.is_playing:
                    self.queue.append(song_info)
                    queue_position = len(self.queue)
                    await self.highrise.chat(f"🎵 Sıraya eklendi (Sıra #{queue_position}): {song_info[1]}")
                else:
                    await self.play_song_with_info(*song_info)
            except Exception as e:
                await self.highrise.chat("❌ Hata: Şarkı bulunamadı")
                print(f"Error: {e}")

        elif message.startswith("!skip"):
            await self.skip_song()

    async def play_song_with_info(self, youtube_url: str, title: str, duration: int) -> None:
        try:
            minutes = duration // 60
            seconds = duration % 60
            await self.highrise.chat(f"✅ Şimdi Çalıyor: {title} [{minutes}:{seconds:02d}]")
            self.current_song = title
            self.is_playing = True

            self.should_stop = False

            # Timer to stop playing song after its duration ends
            def stop_after_duration():
                time.sleep(duration)  # Do not skip automatically, just end the song

            # Start timer in a separate thread
            threading.Thread(target=stop_after_duration, daemon=True).start()

            def stream_thread():
                self.stream_to_zeno(youtube_url)
                if not self.should_stop and self.queue:
                    next_song_info = self.queue.pop(0)  # Get the next song from the queue
                    asyncio.run(self.play_song_with_info(*next_song_info))
                else:
                    self.is_playing = False
                    self.current_song = None

            self.current_thread = Thread(target=stream_thread)
            self.current_thread.start()

        except Exception as e:
            await self.highrise.chat("❌ Error: Could not find or play the song")
            print(f"Error: {e}")

    async def skip_song(self) -> None:
        if not self.is_playing:
            await self.highrise.chat("❌ Şu anda çalan şarkı yok")
            return

        if not self.queue:
            await self.highrise.chat("❌ Sırada geçilebilecek şarkı yok")
            return

        await self.highrise.chat(f"⏭️ Şarkı geçiliyor...")

        # Stop the current song
        self.should_stop = True
        self.is_playing = False

        if hasattr(self, 'process'):
            try:
                self.process.terminate()
            except:
                pass

        if self.current_thread and self.current_thread.is_alive():
            try:
                self.current_thread.join(timeout=0.5)
            except:
                pass

        # Start the next song from the queue
        if self.queue:
            next_song_info = self.queue.pop(0)  # Get the next song from the queue
            self.current_thread = None
            await self.play_song_with_info(*next_song_info)
        else:
            self.is_playing = False
            self.current_song = None

    async def search_youtube(self, query: str) -> tuple:
        ydl_opts = {
            'format': 'bestaudio[ext=m4a]/bestaudio/best',
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'force_generic_extractor': False,
            'nocheckcertificate': True,
            'ignoreerrors': False,
            'logtostderr': False,
            'no_warnings': True,
            'cookiefile': os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cookies.txt')
        }
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            try:
                info_dict = ydl.extract_info(f"ytsearch:{query}", download=False)
                video_info = info_dict['entries'][0]
                url = video_info.get('url', None)
                if not url:
                    formats = video_info.get('formats', [])
                    url = formats[-1]['url'] if formats else video_info['webpage_url']
                return (url, video_info['title'], video_info['duration'])
            except Exception as e:
                print(f"YouTube search error: {str(e)}")
                raise

    async def announce_next_song(self):
        pass #This function is intentionally left empty as per the provided changes.

    def stream_to_zeno(self, youtube_url: str) -> None:
        try:
            start_time = time.time()
            current_duration = None
            if self.queue:
                _, _, current_duration = self.queue[0]
            self.process = (
                ffmpeg
                .input(youtube_url, re=None)
                .output(
                    'icecast://source:cLFZ6mco@link.zeno.fm:80/gke8ym40ryjtv',
                    acodec='libmp3lame',
                    ar='44100',
                    ac='2',
                    ab='128k',
                    content_type='audio/mpeg',
                    f='mp3',
                    ice_name='Highrise Radio',
                    ice_description='Live Radio Stream',
                    reconnect=True,
                    reconnect_streamed=True,
                    reconnect_delay_max=5
                )
                .overwrite_output()
                .run_async(cmd='ffmpeg')
            )
            self.process.wait()
            elapsed_time = time.time() - start_time

            # Şarkı bitti, şimdi sıradakini çal
            if not self.should_stop and (not current_duration or elapsed_time >= current_duration * 0.100):  # %95'ini çaldıysa tamamlandı say
                if self.queue:
                    next_song = self.queue.pop(0)
                    youtube_url, title, duration = next_song
                    self.current_song = title
                    self.is_playing = True
                    # Yeni şarkı mesajını ayrı bir thread'de gönder
                    Thread(target=lambda: asyncio.run(self.send_now_playing_message(title, duration))).start()
                    # Yeni şarkıyı başlat
                    self.stream_to_zeno(youtube_url)
                else:
                    self.is_playing = False
                    self.current_song = None
        except ffmpeg.Error as e:
            print(f"FFmpeg error occurred: {e.stderr.decode() if e.stderr else 'Unknown error'}")

    async def send_now_playing_message(self, title: str, duration: int) -> None:
        try:
            await self.highrise.chat(f"✅ Şimdi Çalıyor: {title} [{duration//60}:{duration%60:02d}]")
        except Exception as e:
            print(f"Error sending message: {e}")


# Bot definition and bot loop
class RunBot():
    room_id = "6828f1aa281d704355d5c6f8"  # Updated Room ID
    bot_token = "0b89956c18f0384e1c1d7d95b0efb2fc4a25b75b139fc7af9385af9ea94d470e"  # Updated Bot API Token
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
                traceback.print_exc()  # This will print the full traceback
                time.sleep(1)
                continue

# Running both Web Server and Bot
if __name__ == "__main__":
    WebServer().keep_alive()  # Keeps the bot alive
    RunBot().run_loop()