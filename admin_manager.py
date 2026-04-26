
import json
import os

def save_admins(admin_list):
    from backup_manager import safe_json_save
    return safe_json_save('admins.json', admin_list)

def load_admins():
    try:
        if os.path.exists('admins.json'):
            if os.path.getsize('admins.json') < 5:
                from backup_manager import restore_from_backup
                if restore_from_backup('admins.json'):
                    print("Admin list restored from backup")
                    
            with open('admins.json', 'r', encoding='utf-8') as f:
                admins = json.load(f)
                return admins if isinstance(admins, list) else []
        return []
    except Exception as e:
        print(f"Error loading admins: {e}")
        from backup_manager import restore_from_backup
        if restore_from_backup('admins.json'):
            try:
                with open('admins.json', 'r', encoding='utf-8') as f:
                    admins = json.load(f)
                    return admins if isinstance(admins, list) else []
            except:
                pass
        return []
