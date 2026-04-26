
import json
import os

def save_queue(queue_data):
    try:
        with open('queue.json', 'w', encoding='utf-8') as f:
            json.dump(queue_data, f, ensure_ascii=False, indent=4)
            f.flush()
            os.fsync(f.fileno())
        return True
    except Exception as e:
        print(f"Error saving queue: {e}")
        return False

def load_queue():
    try:
        if os.path.exists('queue.json'):
            with open('queue.json', 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"Error loading queue: {e}")
    return []
