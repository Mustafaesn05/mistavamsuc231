
import json
import os

def load_user_stats():
    try:
        if os.path.exists('user_stats.json'):
            if os.path.getsize('user_stats.json') < 5:
                from backup_manager import restore_from_backup
                if restore_from_backup('user_stats.json'):
                    print("User stats restored from backup")
                    
            with open('user_stats.json', 'r', encoding='utf-8') as f:
                stats = json.load(f)
                return stats if isinstance(stats, dict) else {}
        return {}
    except Exception as e:
        print(f"Error loading user stats: {e}")
        from backup_manager import restore_from_backup
        if restore_from_backup('user_stats.json'):
            try:
                with open('user_stats.json', 'r', encoding='utf-8') as f:
                    stats = json.load(f)
                    return stats if isinstance(stats, dict) else {}
            except:
                pass
        return {}

def save_user_stats(stats):
    from backup_manager import safe_json_save
    return safe_json_save('user_stats.json', stats)

def increment_song_request(username):
    try:
        stats = load_user_stats()
        if username not in stats:
            stats[username] = {"song_requests": 0}
        stats[username]["song_requests"] += 1
        
        if save_user_stats(stats):
            print(f"Song request incremented for {username}: {stats[username]['song_requests']}")
            return True
        else:
            print(f"Failed to save user stats for {username}")
            return False
    except Exception as e:
        print(f"Error incrementing song request for {username}: {e}")
        return False
