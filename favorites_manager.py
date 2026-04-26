
import json
import os

def save_favorites(favorites_data):
    from backup_manager import safe_json_save
    return safe_json_save('favorites.json', favorites_data)

def load_favorites():
    try:
        if os.path.exists('favorites.json'):
            if os.path.getsize('favorites.json') < 5:
                from backup_manager import restore_from_backup
                if restore_from_backup('favorites.json'):
                    print("Favorites restored from backup")
                    
            with open('favorites.json', 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"Error loading favorites: {e}")
        from backup_manager import restore_from_backup
        if restore_from_backup('favorites.json'):
            try:
                with open('favorites.json', 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
    return {}

def add_favorite(username, song_info):
    favorites = load_favorites()
    if username not in favorites:
        favorites[username] = []
    
    # Şarkı başlığına göre kontrol et
    title = song_info['title']
    if not any(fav['title'] == title for fav in favorites[username]):
        favorites[username].append(song_info)
        save_favorites(favorites)
        return True
    return False

def get_user_favorites(username):
    favorites = load_favorites()
    return favorites.get(username, [])

def remove_favorite(username, indices):
    favorites = load_favorites()
    if username not in favorites:
        return False
    
    user_favorites = favorites[username]
    indices = sorted(indices, reverse=True)
    
    try:
        for index in indices:
            if 0 <= index - 1 < len(user_favorites):
                user_favorites.pop(index - 1)
        
        favorites[username] = user_favorites
        save_favorites(favorites)
        return True
    except:
        return False
