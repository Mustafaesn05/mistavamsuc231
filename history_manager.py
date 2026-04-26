
import json
import os

def save_history(song_info):
    try:
        history = load_history()
        history.append(song_info)
        # Keep only last 10 songs
        if len(history) > 10:
            history = history[-10:]
            
        with open('song_history.json', 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=4)
            f.flush()
            os.fsync(f.fileno())
        return True
    except Exception as e:
        print(f"Error saving history: {e}")
        return False

def load_history():
    try:
        if os.path.exists('song_history.json'):
            with open('song_history.json', 'r', encoding='utf-8') as f:
                history = json.load(f)
                return history if isinstance(history, list) else []
        return []
    except Exception as e:
        print(f"Error loading history: {e}")
        return []
