
import json
import os

def save_blacklist(blacklist):
    from backup_manager import safe_json_save
    return safe_json_save('blacklist.json', blacklist)

def load_blacklist():
    try:
        if os.path.exists('blacklist.json'):
            if os.path.getsize('blacklist.json') < 5:
                from backup_manager import restore_from_backup
                if restore_from_backup('blacklist.json'):
                    print("Blacklist restored from backup")
                    
            with open('blacklist.json', 'r', encoding='utf-8') as f:
                blacklist = json.load(f)
                return blacklist if isinstance(blacklist, list) else []
        return []
    except Exception as e:
        print(f"Error loading blacklist: {e}")
        from backup_manager import restore_from_backup
        if restore_from_backup('blacklist.json'):
            try:
                with open('blacklist.json', 'r', encoding='utf-8') as f:
                    blacklist = json.load(f)
                    return blacklist if isinstance(blacklist, list) else []
            except:
                pass
        return []
