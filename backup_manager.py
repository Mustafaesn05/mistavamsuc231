
import json
import os
import shutil
from datetime import datetime

def ensure_backup_folder():
    """Yedekler klasörünün var olduğundan emin olur"""
    backup_folder = "yedekler"
    if not os.path.exists(backup_folder):
        os.makedirs(backup_folder)
    return backup_folder

def create_backup(file_path):
    """Belirtilen dosyanın yedeğini oluşturur - tek backup dosyası"""
    if not os.path.exists(file_path):
        return False
    
    try:
        backup_folder = ensure_backup_folder()
        filename = os.path.basename(file_path)
        backup_filename = f"{filename}.backup"
        backup_path = os.path.join(backup_folder, backup_filename)
        
        shutil.copy2(file_path, backup_path)
        return True
    except Exception as e:
        print(f"Backup oluşturulurken hata: {e}")
        return False

def should_backup(old_data, new_data):
    """Yedek alınıp alınmayacağını belirler - sadece veri eklendi/güncellendi mi?"""
    try:
        # Eğer eski veri yoksa (yeni dosya), yedek alma
        if not old_data:
            return False
            
        # Eğer yeni veri boş veya None ise, yedek alma (silme durumu)
        if not new_data or new_data == {} or new_data == []:
            return False
        
        # Veri tipine göre kontrol
        if isinstance(old_data, dict) and isinstance(new_data, dict):
            # Yeni anahtarlar eklendi mi veya değerler arttı mı?
            for key in new_data:
                if key not in old_data:
                    return True  # Yeni anahtar eklendi
                if isinstance(new_data[key], dict) and isinstance(old_data[key], dict):
                    # İç içe dict kontrolü
                    if len(new_data[key]) > len(old_data[key]):
                        return True
                    # Points gibi sayısal değerlerde artış var mı?
                    if "points" in new_data[key] and "points" in old_data[key]:
                        if new_data[key]["points"] > old_data[key]["points"]:
                            return True
                    if "gold" in new_data[key] and "gold" in old_data[key]:
                        if new_data[key]["gold"] > old_data[key]["gold"]:
                            return True
                elif isinstance(new_data[key], (int, float)) and isinstance(old_data[key], (int, float)):
                    if new_data[key] > old_data[key]:
                        return True  # Sayısal değer arttı
        
        elif isinstance(old_data, list) and isinstance(new_data, list):
            # Liste boyutu arttı mı?
            if len(new_data) > len(old_data):
                return True
                
        return False  # Diğer durumlarda yedek alma
        
    except Exception as e:
        print(f"Backup kontrolü sırasında hata: {e}")
        return False

def safe_json_save(file_path, data, indent=4):
    """JSON dosyasını güvenli bir şekilde kaydeder ve gerektiğinde backup alır"""
    try:
        # Mevcut veriyi yükle
        old_data = None
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    old_data = json.load(f)
            except:
                old_data = None
        
        # Yedek alınmalı mı kontrol et
        if should_backup(old_data, data):
            create_backup(file_path)
        
        # Geçici dosyaya yaz
        temp_file = file_path + '.tmp'
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=indent)
            f.flush()
            os.fsync(f.fileno())
        
        # Dosya boyutunu kontrol et
        if os.path.getsize(temp_file) > 5:  # En az 5 byte olmalı
            # Atomic move operation
            if os.name == 'nt':  # Windows
                if os.path.exists(file_path):
                    os.remove(file_path)
                os.rename(temp_file, file_path)
            else:  # Unix/Linux
                os.rename(temp_file, file_path)
            return True
        else:
            if os.path.exists(temp_file):
                os.remove(temp_file)
            return False
            
    except Exception as e:
        print(f"JSON kaydetme hatası ({file_path}): {e}")
        # Geçici dosyayı temizle
        if os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except:
                pass
        return False

def restore_from_backup(file_path):
    """Dosyayı backup'tan geri yükler"""
    try:
        backup_folder = "yedekler"
        if not os.path.exists(backup_folder):
            return False
        
        filename = os.path.basename(file_path)
        backup_filename = f"{filename}.backup"
        backup_path = os.path.join(backup_folder, backup_filename)
        
        if not os.path.exists(backup_path):
            return False
        
        shutil.copy2(backup_path, file_path)
        print(f"Dosya backup'tan geri yüklendi: {file_path}")
        return True
        
    except Exception as e:
        print(f"Backup'tan geri yükleme hatası: {e}")
        return False
