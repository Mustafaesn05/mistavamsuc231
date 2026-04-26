
import json
import os

def load_ratings():
    """Load song ratings from JSON file"""
    try:
        if os.path.exists('song_ratings.json'):
            with open('song_ratings.json', 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    except Exception as e:
        print(f"Error loading ratings: {e}")
        return {}

def save_ratings(ratings):
    """Save song ratings to JSON file"""
    try:
        with open('song_ratings.json', 'w', encoding='utf-8') as f:
            json.dump(ratings, f, ensure_ascii=False, indent=4)
            f.flush()
            os.fsync(f.fileno())
        return True
    except Exception as e:
        print(f"Error saving ratings: {e}")
        return False

def add_rating(song_title, username, rating):
    """Add a rating for a song"""
    ratings = load_ratings()
    
    # Initialize song if it doesn't exist
    if song_title not in ratings:
        ratings[song_title] = {
            "ratings": [],
            "total_rating": 0,
            "rating_count": 0,
            "average_rating": 0.0
        }
    
    # Check if user already rated this song
    user_already_rated = any(r["username"] == username for r in ratings[song_title]["ratings"])
    if user_already_rated:
        return False, "Bu şarkıyı zaten puanladınız!"
    
    # Add the new rating
    ratings[song_title]["ratings"].append({
        "username": username,
        "rating": rating
    })
    
    # Update statistics
    ratings[song_title]["total_rating"] += rating
    ratings[song_title]["rating_count"] += 1
    ratings[song_title]["average_rating"] = ratings[song_title]["total_rating"] / ratings[song_title]["rating_count"]
    
    if save_ratings(ratings):
        return True, f"Şarkıya {rating}/10 puan verdiniz! Ortalama puan: {ratings[song_title]['average_rating']:.1f}"
    else:
        return False, "Puan kaydedilirken bir hata oluştu!"

def get_top_rated_songs(limit=5):
    """Get top rated songs using weighted scoring system"""
    ratings = load_ratings()
    
    # Filter songs that have at least one rating
    rated_songs = [(song, data) for song, data in ratings.items() if data["rating_count"] > 0]
    
    # Calculate weighted score for each song
    for song, data in rated_songs:
        avg_rating = data["average_rating"]
        vote_count = data["rating_count"]
        
        # Improved weighted score formula
        # Base score is the average rating (primary factor)
        base_score = avg_rating
        
        # Confidence multiplier based on vote count (0.7 to 1.0)
        # Even 1 vote gets 70% confidence, full confidence at 5+ votes
        confidence_multiplier = 0.7 + min(vote_count / 5.0, 0.3)
        
        # Small bonus for having more votes (max 0.5 points)
        vote_bonus = min(vote_count * 0.05, 0.5)
        
        # Final weighted score
        weighted_score = (base_score * confidence_multiplier) + vote_bonus
        data["weighted_score"] = weighted_score
    
    # Sort by weighted score (descending)
    sorted_songs = sorted(rated_songs, key=lambda x: -x[1]["weighted_score"])
    
    return sorted_songs[:limit]

def get_song_rating(song_title):
    """Get rating information for a specific song"""
    ratings = load_ratings()
    return ratings.get(song_title, None)
