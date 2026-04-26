
import json
import os

def save_blocked_songs(blocked_songs):
    try:
        with open('blocked_songs.json', 'w', encoding='utf-8') as f:
            json.dump(blocked_songs, f, ensure_ascii=False, indent=4)
            f.flush()
            os.fsync(f.fileno())
        return True
    except Exception as e:
        print(f"Error saving blocked songs: {e}")
        return False

def load_blocked_songs():
    try:
        if os.path.exists('blocked_songs.json'):
            with open('blocked_songs.json', 'r', encoding='utf-8') as f:
                blocked_songs = json.load(f)
                return blocked_songs if isinstance(blocked_songs, list) else []
        return []
    except Exception as e:
        print(f"Error loading blocked songs: {e}")
        return []
