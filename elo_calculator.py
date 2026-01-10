import math
import json
import os
import shutil
import random
from datetime import datetime
from collections import defaultdict

# --- Configuration ---
INITIAL_RATING = 1500.0
K_FACTOR_BASE = 40
K_FACTOR_EARLY = 50
EARLY_MATCHES_THRESHOLD = 5

GD_MULTIPLIERS = {
    1: 1.0,
    2: 1.3,
    3: 1.5,
    4: 1.65,
    5: 1.75
}

HOME_ADVANTAGE = 60.0

JSON_FILENAME = "elo_championship_data.json"
BACKUP_DIR = "backups"

# --- Backup Functions ---

def create_backup(filename):
    """Creates a timestamped backup of the data file."""
    if not os.path.exists(filename):
        return
    
    os.makedirs(BACKUP_DIR, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_name = f"backup_{timestamp}.json"
    backup_path = os.path.join(BACKUP_DIR, backup_name)
    
    try:
        shutil.copy2(filename, backup_path)
    except Exception as e:
        print(f"Warning: Could not create backup: {e}")

def list_backups():
    """Lists available backups."""
    if not os.path.exists(BACKUP_DIR):
        return []
    
    backups = [f for f in os.listdir(BACKUP_DIR) if f.startswith('backup_') and f.endswith('.json')]
    backups.sort(reverse=True)
    return backups

def restore_backup(backup_name, filename):
    """Restores data from a backup file."""
    backup_path = os.path.join(BACKUP_DIR, backup_name)
    if not os.path.exists(backup_path):
        print(f"Error: Backup file '{backup_name}' not found.")
        return False
    
    try:
        # Create backup of current file before restoring
        if os.path.exists(filename):
            create_backup(filename)
        
        shutil.copy2(backup_path, filename)
        print(f"Successfully restored from backup: {backup_name}")
        return True
    except Exception as e:
        print(f"Error restoring backup: {e}")
        return False

# --- Persistence Functions ---

def load_data(filename):
    """Loads ratings, match history, and match counts from JSON file."""
    if os.path.exists(filename):
        try:
            with open(filename, 'r') as f:
                content = f.read()
                if not content:
                    print(f"Data file '{filename}' is empty. Starting fresh.")
                    return {}, [], {}
                
                data = json.loads(content)
                ratings = {team: float(rating) for team, rating in data.get('ratings', {}).items()}
                match_history = data.get('match_history', [])
                match_counts = {team: int(count) for team, count in data.get('match_counts', {}).items()}
                
                print(f"Successfully loaded data from '{filename}'.")
                print(f"Loaded {len(ratings)} teams and {len(match_history)} matches.")
                return ratings, match_history, match_counts
        except json.JSONDecodeError:
            print(f"Error: Could not decode JSON from '{filename}'.")
            return {}, [], {}
        except Exception as e:
            print(f"An error occurred while loading '{filename}': {e}")
            return {}, [], {}
    else:
        print(f"Data file '{filename}' not found. Starting fresh.")
        return {}, [], {}

def save_data(ratings, match_history, match_counts, filename):
    """Saves ratings, match history, and match counts to JSON file."""
    try:
        data = {
            'ratings': ratings,
            'match_history': match_history,
            'match_counts': match_counts,
            'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        with open(filename, 'w') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"Error: Could not save data to '{filename}': {e}")

# --- Elo Functions ---

def calculate_expected_score(rating_a, rating_b, home_advantage=0):
    """Calculates the expected score for Team A."""
    try:
        rating_a = float(rating_a) + home_advantage
        rating_b = float(rating_b)
    except ValueError:
        print(f"Error: Invalid rating format ({rating_a}, {rating_b})")
        return 0.5
    return 1 / (1 + math.pow(10, (rating_b - rating_a) / 400))

def get_goal_diff_multiplier(goal_diff):
    """Returns the K-factor multiplier based on goal difference."""
    if goal_diff <= 0:
        return 1.0
    return GD_MULTIPLIERS.get(goal_diff, GD_MULTIPLIERS[5])

def determine_k_factor(team_a_matches, team_b_matches):
    """Determines K-factor based on team experience."""
    avg_matches = (team_a_matches + team_b_matches) / 2
    
    if avg_matches < EARLY_MATCHES_THRESHOLD:
        progress = avg_matches / EARLY_MATCHES_THRESHOLD
        return K_FACTOR_EARLY - (K_FACTOR_EARLY - K_FACTOR_BASE) * progress
    return K_FACTOR_BASE

def calculate_rating_changes(rating_a, rating_b, matches_a, matches_b, goals_a, goals_b, is_home_a):
    """
    Calculates what the rating changes would be for a match.
    Returns dict with all match details.
    """
    home_adv = 0
    if is_home_a is True:
        home_adv = HOME_ADVANTAGE
    elif is_home_a is False:
        home_adv = -HOME_ADVANTAGE

    if goals_a > goals_b:
        score_a, score_b = 1.0, 0.0
        goal_diff = goals_a - goals_b
        winner = 'team_a'
    elif goals_b > goals_a:
        score_a, score_b = 0.0, 1.0
        goal_diff = goals_b - goals_a
        winner = 'team_b'
    else:
        score_a, score_b = 0.5, 0.5
        goal_diff = 0
        winner = None

    expected_a = calculate_expected_score(rating_a, rating_b, home_adv)
    expected_b = 1 - expected_a

    k_base = determine_k_factor(matches_a, matches_b)
    
    if winner:
        gd_multiplier = get_goal_diff_multiplier(goal_diff)
        k_adjusted = k_base * gd_multiplier
    else:
        k_adjusted = k_base

    change_a = k_adjusted * (score_a - expected_a)
    change_b = k_adjusted * (score_b - expected_b)
    
    return {
        'change_a': change_a,
        'change_b': change_b,
        'expected_a': expected_a,
        'expected_b': expected_b,
        'k_adjusted': k_adjusted,
        'k_base': k_base,
        'gd_multiplier': get_goal_diff_multiplier(goal_diff) if winner else 1.0
    }

def update_ratings(ratings, match_counts, match_history, team_a, team_b, goals_a, goals_b, is_home_a=None):
    """Updates Elo ratings and records match in history."""
    rating_a = float(ratings.get(team_a, INITIAL_RATING))
    rating_b = float(ratings.get(team_b, INITIAL_RATING))
    matches_a = match_counts.get(team_a, 0)
    matches_b = match_counts.get(team_b, 0)

    # Calculate changes
    changes = calculate_rating_changes(rating_a, rating_b, matches_a, matches_b, goals_a, goals_b, is_home_a)
    
    new_rating_a = rating_a + changes['change_a']
    new_rating_b = rating_b + changes['change_b']

    # Store match in history BEFORE updating ratings
    match_record = {
        'match_id': len(match_history) + 1,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'team_a': team_a,
        'team_b': team_b,
        'goals_a': goals_a,
        'goals_b': goals_b,
        'is_home_a': is_home_a,
        'rating_a_before': rating_a,
        'rating_b_before': rating_b,
        'rating_a_after': new_rating_a,
        'rating_b_after': new_rating_b,
        'change_a': changes['change_a'],
        'change_b': changes['change_b']
    }
    match_history.append(match_record)

    # Update ratings
    ratings[team_a] = new_rating_a
    ratings[team_b] = new_rating_b
    match_counts[team_a] = matches_a + 1
    match_counts[team_b] = matches_b + 1

    # Calculate three-outcome probabilities
    home_adv = 0
    if is_home_a is True:
        home_adv = HOME_ADVANTAGE
    elif is_home_a is False:
        home_adv = -HOME_ADVANTAGE
    
    adjusted_rating_a = rating_a + home_adv
    rating_diff = adjusted_rating_a - rating_b
    abs_diff = abs(rating_diff)
    
    # Calculate draw probability
    if abs_diff <= 100:
        draw_prob = 0.27 - (abs_diff / 100) * 0.02
    elif abs_diff <= 200:
        draw_prob = 0.25 - ((abs_diff - 100) / 100) * 0.05
    elif abs_diff <= 300:
        draw_prob = 0.20 - ((abs_diff - 200) / 100) * 0.05
    else:
        draw_prob = max(0.15 - ((abs_diff - 300) / 200) * 0.05, 0.08)
    
    # Adjust win probabilities
    remaining_prob = 1.0 - draw_prob
    win_a_prob = changes['expected_a'] * remaining_prob
    win_b_prob = changes['expected_b'] * remaining_prob

    # Display results
    result_str = f"{team_a} {goals_a} - {goals_b} {team_b}"
    home_indicator = " (H)" if is_home_a is True else " (A)" if is_home_a is False else ""
    
    print(f"\nMatch #{match_record['match_id']}: {result_str}{home_indicator}")
    print(f"Ratings: {team_a} {new_rating_a:.1f} ({changes['change_a']:+.1f}) | {team_b} {new_rating_b:.1f} ({changes['change_b']:+.1f})")
    print(f"Pre-match probabilities: {team_a} {win_a_prob*100:.1f}% | Draw {draw_prob*100:.1f}% | {team_b} {win_b_prob*100:.1f}%")

def recalculate_all_ratings(match_history):
    """
    Recalculates all ratings from scratch based on match history.
    Used after deleting or editing matches.
    """
    ratings = {}
    match_counts = {}
    
    for match in match_history:
        team_a = match['team_a']
        team_b = match['team_b']
        
        rating_a = ratings.get(team_a, INITIAL_RATING)
        rating_b = ratings.get(team_b, INITIAL_RATING)
        matches_a = match_counts.get(team_a, 0)
        matches_b = match_counts.get(team_b, 0)
        
        changes = calculate_rating_changes(
            rating_a, rating_b, matches_a, matches_b,
            match['goals_a'], match['goals_b'], match['is_home_a']
        )
        
        ratings[team_a] = rating_a + changes['change_a']
        ratings[team_b] = rating_b + changes['change_b']
        match_counts[team_a] = matches_a + 1
        match_counts[team_b] = matches_b + 1
        
        # Update match record with recalculated values
        match['rating_a_before'] = rating_a
        match['rating_b_before'] = rating_b
        match['rating_a_after'] = ratings[team_a]
        match['rating_b_after'] = ratings[team_b]
        match['change_a'] = changes['change_a']
        match['change_b'] = changes['change_b']
    
    return ratings, match_counts

# --- Helper Functions ---

def display_rankings(ratings, match_counts):
    """Displays team rankings with additional statistics."""
    if not ratings:
        print("\nNo teams or ratings available yet.")
        return

    sorted_teams = sorted(ratings.items(), key=lambda item: item[1], reverse=True)

    print("\n" + "="*70)
    print("ELO RANKINGS")
    print("="*70)
    print(f"{'Rank':<6} {'Team':<25} {'Rating':<10} {'Matches':<8} {'Status'}")
    print("-" * 70)
    
    for i, (team, rating) in enumerate(sorted_teams, 1):
        matches = match_counts.get(team, 0)
        status = "Provisional" if matches < EARLY_MATCHES_THRESHOLD else "Established"
        print(f"{i:<6} {team:<25} {rating:<10.1f} {matches:<8} {status}")
    
    print("-" * 70)
    print(f"Total Teams: {len(sorted_teams)}\n")

def display_match_history(match_history, limit=10):
    """Displays recent match history."""
    if not match_history:
        print("\nNo matches recorded yet.")
        return
    
    print(f"\n--- Recent Match History (showing last {min(limit, len(match_history))} matches) ---")
    
    # Show most recent matches first
    recent_matches = match_history[-limit:] if len(match_history) > limit else match_history
    recent_matches = list(reversed(recent_matches))
    
    for match in recent_matches:
        home_str = ""
        if match['is_home_a'] is True:
            home_str = " (H)"
        elif match['is_home_a'] is False:
            home_str = " (A)"
        
        print(f"\nMatch #{match['match_id']} - {match['timestamp']}")
        print(f"  {match['team_a']}{home_str if match['is_home_a'] is True else ''} "
              f"{match['goals_a']} - {match['goals_b']} "
              f"{match['team_b']}{home_str if match['is_home_a'] is False else ''}")
        print(f"  Rating changes: {match['team_a']} ({match['change_a']:+.1f}), "
              f"{match['team_b']} ({match['change_b']:+.1f})")

def undo_last_match(ratings, match_history, match_counts, filename):
    """Removes the last match and recalculates all ratings."""
    if not match_history:
        print("\nNo matches to undo.")
        return
    
    last_match = match_history[-1]
    print(f"\nLast match: {last_match['team_a']} {last_match['goals_a']} - "
          f"{last_match['goals_b']} {last_match['team_b']}")
    
    confirm = input("Are you sure you want to undo this match? (yes/no): ").lower().strip()
    if confirm != 'yes':
        print("Undo cancelled.")
        return
    
    # Remove last match
    match_history.pop()
    
    # Recalculate everything
    new_ratings, new_counts = recalculate_all_ratings(match_history)
    ratings.clear()
    ratings.update(new_ratings)
    match_counts.clear()
    match_counts.update(new_counts)
    
    save_data(ratings, match_history, match_counts, filename)
    print("Last match removed and ratings recalculated.")

def delete_match(ratings, match_history, match_counts, filename):
    """Deletes a specific match by ID and recalculates ratings."""
    if not match_history:
        print("\nNo matches to delete.")
        return
    
    display_match_history(match_history, limit=20)
    
    try:
        match_id = int(input("\nEnter the Match ID to delete: ").strip())
    except ValueError:
        print("Invalid input.")
        return
    
    # Find match
    match_index = None
    for i, match in enumerate(match_history):
        if match['match_id'] == match_id:
            match_index = i
            break
    
    if match_index is None:
        print(f"Match #{match_id} not found.")
        return
    
    match = match_history[match_index]
    print(f"\nMatch to delete: {match['team_a']} {match['goals_a']} - "
          f"{match['goals_b']} {match['team_b']}")
    
    confirm = input("Are you sure you want to delete this match? (yes/no): ").lower().strip()
    if confirm != 'yes':
        print("Delete cancelled.")
        return
    
    # Remove match
    match_history.pop(match_index)
    
    # Renumber match IDs
    for i, m in enumerate(match_history, 1):
        m['match_id'] = i
    
    # Recalculate everything
    new_ratings, new_counts = recalculate_all_ratings(match_history)
    ratings.clear()
    ratings.update(new_ratings)
    match_counts.clear()
    match_counts.update(new_counts)
    
    save_data(ratings, match_history, match_counts, filename)
    print("Match deleted and ratings recalculated.")

def edit_match(ratings, match_history, match_counts, filename):
    """Edits a specific match and recalculates ratings."""
    if not match_history:
        print("\nNo matches to edit.")
        return
    
    display_match_history(match_history, limit=20)
    
    try:
        match_id = int(input("\nEnter the Match ID to edit: ").strip())
    except ValueError:
        print("Invalid input.")
        return
    
    # Find match
    match_index = None
    for i, match in enumerate(match_history):
        if match['match_id'] == match_id:
            match_index = i
            break
    
    if match_index is None:
        print(f"Match #{match_id} not found.")
        return
    
    match = match_history[match_index]
    print(f"\nCurrent match: {match['team_a']} {match['goals_a']} - "
          f"{match['goals_b']} {match['team_b']}")
    
    # Get new values
    print("\nEnter new values (press Enter to keep current value):")
    
    new_goals_a = input(f"Goals for {match['team_a']} (current: {match['goals_a']}): ").strip()
    new_goals_b = input(f"Goals for {match['team_b']} (current: {match['goals_b']}): ").strip()
    
    try:
        if new_goals_a:
            match['goals_a'] = int(new_goals_a)
        if new_goals_b:
            match['goals_b'] = int(new_goals_b)
    except ValueError:
        print("Invalid input. Edit cancelled.")
        return
    
    # Recalculate everything
    new_ratings, new_counts = recalculate_all_ratings(match_history)
    ratings.clear()
    ratings.update(new_ratings)
    match_counts.clear()
    match_counts.update(new_counts)
    
    save_data(ratings, match_history, match_counts, filename)
    print("Match edited and ratings recalculated.")

def add_match_result(ratings, match_counts, match_history):
    """Prompts user for match details and updates ratings."""
    print("\n--- Add Match Result ---")
    
    while True:
        team_a = input("Home team: ").strip()
        if team_a: break
        print("Team name cannot be empty.")
    
    while True:
        team_b = input(f"Away team: ").strip()
        if team_b and team_b != team_a: break
        elif team_b == team_a: print("Teams must be different.")
        else: print("Team name cannot be empty.")

    while True:
        try:
            goals_a = int(input(f"Goals {team_a}: ").strip())
            if goals_a >= 0: break
            print("Goals cannot be negative.")
        except ValueError: 
            print("Invalid input.")
    
    while True:
        try:
            goals_b = int(input(f"Goals {team_b}: ").strip())
            if goals_b >= 0: break
            print("Goals cannot be negative.")
        except ValueError: 
            print("Invalid input.")

    # Ask if this is actually a neutral venue match
    while True:
        neutral_input = input(f"Neutral venue? (y/n, default=n): ").strip().lower()
        if neutral_input == 'y' or neutral_input == 'yes':
            is_home_a = None
            break
        elif neutral_input == 'n' or neutral_input == 'no' or neutral_input == '':
            is_home_a = True
            break
        print("Invalid input.")

    update_ratings(ratings, match_counts, match_history, team_a, team_b, goals_a, goals_b, is_home_a)

def predict_match(ratings, match_counts):
    """Predicts the outcome of an upcoming match."""
    print("\n--- Match Prediction ---")
    
    while True:
        team_a = input("Home team: ").strip()
        if team_a in ratings: break
        elif team_a: print(f"Team '{team_a}' not found.")
        else: print("Team name cannot be empty.")
    
    while True:
        team_b = input("Away team: ").strip()
        if team_b in ratings and team_b != team_a: break
        elif team_b == team_a: print("Teams must be different.")
        elif team_b: print(f"Team '{team_b}' not found.")
        else: print("Team name cannot be empty.")
    
    # Ask if neutral venue
    while True:
        neutral_input = input(f"Neutral venue? (y/n, default=n): ").strip().lower()
        if neutral_input == 'y' or neutral_input == 'yes':
            is_home_a = None
            break
        elif neutral_input == 'n' or neutral_input == 'no' or neutral_input == '':
            is_home_a = True
            break
        print("Invalid input.")
    
    rating_a = ratings[team_a]
    rating_b = ratings[team_b]
    matches_a = match_counts.get(team_a, 0)
    matches_b = match_counts.get(team_b, 0)
    
    home_adv = 0
    venue_type = "Neutral"
    if is_home_a is True:
        home_adv = HOME_ADVANTAGE
        venue_type = f"{team_a} (Home)"
    
    # Calculate adjusted ratings
    adjusted_rating_a = rating_a + home_adv
    rating_diff = adjusted_rating_a - rating_b
    abs_diff = abs(rating_diff)
    
    # Calculate win probabilities using Elo formula
    expected_a = calculate_expected_score(rating_a, rating_b, home_adv)
    expected_b = 1 - expected_a
    
    # Calculate draw probability
    if abs_diff <= 100:
        draw_prob = 0.27 - (abs_diff / 100) * 0.02
    elif abs_diff <= 200:
        draw_prob = 0.25 - ((abs_diff - 100) / 100) * 0.05
    elif abs_diff <= 300:
        draw_prob = 0.20 - ((abs_diff - 200) / 100) * 0.05
    else:
        draw_prob = max(0.15 - ((abs_diff - 300) / 200) * 0.05, 0.08)
    
    # Adjust win probabilities
    remaining_prob = 1.0 - draw_prob
    win_a = expected_a * remaining_prob
    win_b = expected_b * remaining_prob
    
    print(f"\n{team_a} (Elo: {rating_a:.1f}, {matches_a} matches)")
    print(f"vs")
    print(f"{team_b} (Elo: {rating_b:.1f}, {matches_b} matches)")
    print(f"\nVenue: {venue_type}")
    print(f"Rating difference: {abs(rating_diff):.1f} points")
    
    print(f"\nPredicted probabilities:")
    print(f"  {team_a} Win: {win_a*100:.1f}%")
    print(f"  Draw:       {draw_prob*100:.1f}%")
    print(f"  {team_b} Win: {win_b*100:.1f}%")
    
    if matches_a < EARLY_MATCHES_THRESHOLD or matches_b < EARLY_MATCHES_THRESHOLD:
        print("\nNote: One or both teams have provisional ratings")

def backup_and_restore_menu(filename):
    """Menu for backup and restore operations."""
    while True:
        print("\n--- Backup & Restore Menu ---")
        print("  1: Create Manual Backup")
        print("  2: List Available Backups")
        print("  3: Restore from Backup")
        print("  4: Return to Main Menu")
        
        choice = input("\nEnter your choice: ").strip()
        
        if choice == '1':
            create_backup(filename)
        elif choice == '2':
            backups = list_backups()
            if not backups:
                print("\nNo backups available.")
            else:
                print(f"\nAvailable backups ({len(backups)}):")
                for i, backup in enumerate(backups, 1):
                    # Extract timestamp from filename
                    timestamp = backup.replace('backup_', '').replace('.json', '')
                    formatted = datetime.strptime(timestamp, '%Y%m%d_%H%M%S').strftime('%Y-%m-%d %H:%M:%S')
                    print(f"  {i}. {backup} ({formatted})")
        elif choice == '3':
            backups = list_backups()
            if not backups:
                print("\nNo backups available.")
            else:
                print(f"\nAvailable backups:")
                for i, backup in enumerate(backups, 1):
                    timestamp = backup.replace('backup_', '').replace('.json', '')
                    formatted = datetime.strptime(timestamp, '%Y%m%d_%H%M%S').strftime('%Y-%m-%d %H:%M:%S')
                    print(f"  {i}. {backup} ({formatted})")
                
                try:
                    choice_num = int(input("\nEnter backup number to restore (0 to cancel): ").strip())
                    if choice_num == 0:
                        print("Restore cancelled.")
                    elif 1 <= choice_num <= len(backups):
                        if restore_backup(backups[choice_num - 1], filename):
                            print("Please restart the program to load the restored data.")
                            return True  # Signal to reload data
                    else:
                        print("Invalid backup number.")
                except ValueError:
                    print("Invalid input.")
        elif choice == '4':
            break
        else:
            print("Invalid choice.")
    
    return False

def reset_championship(ratings, match_history, match_counts, filename):
    """Clears all data."""
    confirm = input("Are you sure you want to reset all data? This will create a backup first. (yes/no): ").lower().strip()
    if confirm == 'yes':
        create_backup(filename)
        ratings.clear()
        match_history.clear()
        match_counts.clear()
        save_data(ratings, match_history, match_counts, filename)
        print("Championship data has been reset. Backup created.")
    else:
        print("Reset cancelled.")

def rename_team(ratings, match_history, match_counts, filename):
    """Renames a team while preserving all data and updating match history."""
    if not ratings:
        print("\nNo teams exist yet to rename.")
        return

    while True:
        old_name = input("Enter the CURRENT name of the team: ").strip()
        if not old_name:
            print("Team name cannot be empty.")
            continue
        if old_name not in ratings:
            print(f"Error: Team '{old_name}' not found.")
            if input("Try again? (yes/no): ").lower().strip() != 'yes':
                print("Rename cancelled.")
                return
        else:
            break

    while True:
        new_name = input(f"Enter the NEW name for '{old_name}': ").strip()
        if not new_name:
            print("New name cannot be empty.")
        elif new_name == old_name:
            print("New name must be different.")
        elif new_name in ratings:
            print(f"Error: Team '{new_name}' already exists.")
        else:
            break

    try:
        # Update ratings and match counts
        rating = ratings.pop(old_name)
        matches = match_counts.pop(old_name, 0)
        ratings[new_name] = rating
        match_counts[new_name] = matches
        
        # Update match history
        for match in match_history:
            if match['team_a'] == old_name:
                match['team_a'] = new_name
            if match['team_b'] == old_name:
                match['team_b'] = new_name
        
        save_data(ratings, match_history, match_counts, filename)
        print(f"\nSuccessfully renamed '{old_name}' to '{new_name}'.")
        print(f"Rating: {rating:.1f}, Matches: {matches}")
        print(f"Updated {len(match_history)} match records.")
    except Exception as e:
        print(f"Error during rename: {e}")

def rename_team(ratings, match_history, match_counts, filename):
    """Renames a team while preserving all data and updating match history."""
    if not ratings:
        print("\nNo teams exist yet to rename.")
        return

    while True:
        old_name = input("Enter the CURRENT name of the team: ").strip()
        if not old_name:
            print("Team name cannot be empty.")
            continue
        if old_name not in ratings:
            print(f"Error: Team '{old_name}' not found.")
            if input("Try again? (yes/no): ").lower().strip() != 'yes':
                print("Rename cancelled.")
                return
        else:
            break

    while True:
        new_name = input(f"Enter the NEW name for '{old_name}': ").strip()
        if not new_name:
            print("New name cannot be empty.")
        elif new_name == old_name:
            print("New name must be different.")
        elif new_name in ratings:
            print(f"Error: Team '{new_name}' already exists.")
        else:
            break

    try:
        # Update ratings and match counts
        rating = ratings.pop(old_name)
        matches = match_counts.pop(old_name, 0)
        ratings[new_name] = rating
        match_counts[new_name] = matches
        
        # Update match history
        for match in match_history:
            if match['team_a'] == old_name:
                match['team_a'] = new_name
            if match['team_b'] == old_name:
                match['team_b'] = new_name
        
        save_data(ratings, match_history, match_counts, filename)
        print(f"\nSuccessfully renamed '{old_name}' to '{new_name}'.")
        print(f"Rating: {rating:.1f}, Matches: {matches}")
        print(f"Updated {len(match_history)} match records.")
    except Exception as e:
        print(f"Error during rename: {e}")

# --- League Standings Functions ---

def calculate_league_standings(match_history):
    """
    Calculates current league standings from match history.
    Returns dict with team stats: points, wins, draws, losses, goals_for, goals_against, matches_played
    """
    standings = defaultdict(lambda: {
        'points': 0,
        'wins': 0,
        'draws': 0,
        'losses': 0,
        'goals_for': 0,
        'goals_against': 0,
        'matches_played': 0
    })
    
    for match in match_history:
        team_a = match['team_a']
        team_b = match['team_b']
        goals_a = match['goals_a']
        goals_b = match['goals_b']
        
        # Update match counts
        standings[team_a]['matches_played'] += 1
        standings[team_b]['matches_played'] += 1
        
        # Update goals
        standings[team_a]['goals_for'] += goals_a
        standings[team_a]['goals_against'] += goals_b
        standings[team_b]['goals_for'] += goals_b
        standings[team_b]['goals_against'] += goals_a
        
        # Update points and results
        if goals_a > goals_b:
            standings[team_a]['points'] += 3
            standings[team_a]['wins'] += 1
            standings[team_b]['losses'] += 1
        elif goals_b > goals_a:
            standings[team_b]['points'] += 3
            standings[team_b]['wins'] += 1
            standings[team_a]['losses'] += 1
        else:
            standings[team_a]['points'] += 1
            standings[team_a]['draws'] += 1
            standings[team_b]['points'] += 1
            standings[team_b]['draws'] += 1
    
    return dict(standings)

def display_league_table(match_history, ratings):
    """Displays the current league standings table."""
    if not match_history:
        print("\nNo matches played yet.")
        return
    
    standings = calculate_league_standings(match_history)
    
    # Sort by points, then goal difference, then goals scored
    sorted_standings = sorted(
        standings.items(),
        key=lambda x: (
            x[1]['points'],
            x[1]['goals_for'] - x[1]['goals_against'],
            x[1]['goals_for']
        ),
        reverse=True
    )
    
    print("\n" + "="*95)
    print("LEAGUE STANDINGS")
    print("="*95)
    print(f"{'Pos':<4} {'Team':<22} {'MP':<4} {'W':<3} {'D':<3} {'L':<3} {'GF':<4} {'GA':<4} {'GD':<5} {'Pts':<4} {'Elo':<7}")
    print("-" * 95)
    
    for pos, (team, stats) in enumerate(sorted_standings, 1):
        gd = stats['goals_for'] - stats['goals_against']
        elo = ratings.get(team, INITIAL_RATING)
        print(f"{pos:<4} {team:<22} {stats['matches_played']:<4} {stats['wins']:<3} "
              f"{stats['draws']:<3} {stats['losses']:<3} {stats['goals_for']:<4} "
              f"{stats['goals_against']:<4} {gd:+5} {stats['points']:<4} {elo:<7.1f}")
    
    print("-" * 95)
    print("MP=Matches Played, W=Wins, D=Draws, L=Losses, GF=Goals For, GA=Goals Against, GD=Goal Difference\n")

def generate_remaining_fixtures(match_history, all_teams):
    """
    Generates list of remaining fixtures based on round-robin format.
    Each team plays every other team twice (home and away).
    """
    # Track matches already played
    played_matches = set()
    for match in match_history:
        team_a = match['team_a']
        team_b = match['team_b']
        # Store as (home, away) tuple
        played_matches.add((team_a, team_b))
    
    # Generate all possible fixtures (home and away)
    remaining_fixtures = []
    for i, team_a in enumerate(all_teams):
        for team_b in all_teams:
            if team_a != team_b:
                # Check if this fixture (home/away) has been played
                if (team_a, team_b) not in played_matches:
                    remaining_fixtures.append((team_a, team_b))
    
    return remaining_fixtures

def simulate_match(rating_a, rating_b, is_home_a):
    """
    Simulates a single match outcome based on Elo ratings.
    Returns (goals_a, goals_b, points_a, points_b)
    """
    home_adv = HOME_ADVANTAGE if is_home_a else 0
    adjusted_rating_a = rating_a + home_adv
    rating_diff = adjusted_rating_a - rating_b
    abs_diff = abs(rating_diff)
    
    # Calculate probabilities
    expected_a = 1 / (1 + math.pow(10, (rating_b - adjusted_rating_a) / 400))
    expected_b = 1 - expected_a
    
    # Draw probability
    if abs_diff <= 100:
        draw_prob = 0.27 - (abs_diff / 100) * 0.02
    elif abs_diff <= 200:
        draw_prob = 0.25 - ((abs_diff - 100) / 100) * 0.05
    elif abs_diff <= 300:
        draw_prob = 0.20 - ((abs_diff - 200) / 100) * 0.05
    else:
        draw_prob = max(0.15 - ((abs_diff - 300) / 200) * 0.05, 0.08)
    
    remaining_prob = 1.0 - draw_prob
    win_a = expected_a * remaining_prob
    win_b = expected_b * remaining_prob
    
    # Simulate outcome
    rand = random.random()
    if rand < win_a:
        # Team A wins - generate realistic scoreline
        goals_a = random.choices([1, 2, 3, 4, 5], weights=[30, 35, 20, 10, 5])[0]
        goals_b = random.choices([0, 1, 2], weights=[50, 35, 15])[0]
        if goals_a <= goals_b:
            goals_a = goals_b + 1
        return goals_a, goals_b, 3, 0
    elif rand < win_a + draw_prob:
        # Draw
        goals = random.choices([0, 1, 2, 3], weights=[20, 40, 30, 10])[0]
        return goals, goals, 1, 1
    else:
        # Team B wins
        goals_b = random.choices([1, 2, 3, 4, 5], weights=[30, 35, 20, 10, 5])[0]
        goals_a = random.choices([0, 1, 2], weights=[50, 35, 15])[0]
        if goals_b <= goals_a:
            goals_b = goals_a + 1
        return goals_a, goals_b, 0, 3

def simulate_season(standings, ratings, remaining_fixtures, num_simulations=100000):
    """
    Runs Monte Carlo simulation of remaining season.
    Returns statistics about final positions for each team.
    """
    all_teams = list(standings.keys())
    position_counts = {team: defaultdict(int) for team in all_teams}
    points_distribution = {team: [] for team in all_teams}
    
    print(f"\nRunning {num_simulations} season simulations...")
    
    for sim in range(num_simulations):
        # Start with current standings
        sim_standings = {
            team: {
                'points': standings[team]['points'],
                'goals_for': standings[team]['goals_for'],
                'goals_against': standings[team]['goals_against']
            }
            for team in all_teams
        }
        
        # Simulate all remaining fixtures
        for team_a, team_b in remaining_fixtures:
            rating_a = ratings.get(team_a, INITIAL_RATING)
            rating_b = ratings.get(team_b, INITIAL_RATING)
            
            goals_a, goals_b, pts_a, pts_b = simulate_match(rating_a, rating_b, is_home_a=True)
            
            sim_standings[team_a]['points'] += pts_a
            sim_standings[team_a]['goals_for'] += goals_a
            sim_standings[team_a]['goals_against'] += goals_b
            
            sim_standings[team_b]['points'] += pts_b
            sim_standings[team_b]['goals_for'] += goals_b
            sim_standings[team_b]['goals_against'] += goals_a
        
        # Sort final standings
        final_standings = sorted(
            sim_standings.items(),
            key=lambda x: (
                x[1]['points'],
                x[1]['goals_for'] - x[1]['goals_against'],
                x[1]['goals_for']
            ),
            reverse=True
        )
        
        # Record positions and points
        for pos, (team, stats) in enumerate(final_standings, 1):
            position_counts[team][pos] += 1
            if sim == 0 or len(points_distribution[team]) < num_simulations:
                points_distribution[team].append(stats['points'])
    
    return position_counts, points_distribution

def display_season_prediction(match_history, ratings):
    """Displays predicted final standings based on Monte Carlo simulation."""
    if not match_history:
        print("\nNo matches played yet.")
        return
    
    standings = calculate_league_standings(match_history)
    all_teams = list(standings.keys())
    
    if len(all_teams) < 2:
        print("\nNeed at least 2 teams to predict season outcome.")
        return
    
    # Calculate total matches per team in full season
    total_matches_per_team = (len(all_teams) - 1) * 2
    matches_played = standings[all_teams[0]]['matches_played']
    
    print(f"\nChampionship: {len(all_teams)} teams")
    print(f"Season format: {total_matches_per_team} matches per team (home and away)")
    print(f"Progress: {matches_played}/{total_matches_per_team} matches played")
    
    if matches_played >= total_matches_per_team:
        print("\nSeason complete! Final standings:")
        display_league_table(match_history, ratings)
        return
    
    # Generate remaining fixtures
    remaining_fixtures = generate_remaining_fixtures(match_history, all_teams)
    print(f"Remaining fixtures: {len(remaining_fixtures)}")
    
    # Run simulation
    num_sims = 100000
    position_counts, points_dist = simulate_season(standings, ratings, remaining_fixtures, num_sims)
    
    # Calculate statistics
    prediction_stats = {}
    for team in all_teams:
        positions = position_counts[team]
        points = points_dist[team]
        
        # Expected position (weighted average)
        exp_pos = sum(pos * count for pos, count in positions.items()) / num_sims
        
        # Most likely position
        most_likely_pos = max(positions.items(), key=lambda x: x[1])[0]
        
        # Championship probability (finishing 1st)
        champion_prob = (positions.get(1, 0) / num_sims) * 100
        
        # Top 5 probability
        top5_prob = sum(positions.get(pos, 0) for pos in [1, 2, 3, 4, 5]) / num_sims * 100
        
        # Expected points
        exp_points = sum(points) / len(points)
        min_points = min(points)
        max_points = max(points)
        
        prediction_stats[team] = {
            'current_points': standings[team]['points'],
            'expected_position': exp_pos,
            'most_likely_position': most_likely_pos,
            'champion_probability': champion_prob,
            'top5_probability': top5_prob,
            'expected_points': exp_points,
            'points_range': (min_points, max_points),
            'current_position': 0  # Will be filled below
        }
    
    # Add current positions
    sorted_current = sorted(
        standings.items(),
        key=lambda x: (x[1]['points'], x[1]['goals_for'] - x[1]['goals_against']),
        reverse=True
    )
    for pos, (team, _) in enumerate(sorted_current, 1):
        prediction_stats[team]['current_position'] = pos
    
    # Display predictions
    print("\n" + "="*100)
    print("PREDICTED FINAL STANDINGS")
    print(f"Based on {num_sims:,} Monte Carlo simulations")
    print("="*100)
    print(f"{'Team':<22} {'Curr':<5} {'Pts':<4} {'Pred':<6} {'Title':<8} {'Top 5':<8} {'Final':<8} {'Range':<12}")
    print(f"{'':22} {'Pos':<5} {'Now':<4} {'Pos':<6} {'%':<8} {'%':<8} {'Pts':<8} {'(Min-Max)':<12}")
    print("-" * 100)
    
    # Sort by expected position
    sorted_predictions = sorted(
        prediction_stats.items(),
        key=lambda x: x[1]['expected_position']
    )
    
    for team, stats in sorted_predictions:
        print(f"{team:<22} {stats['current_position']:<5} {stats['current_points']:<4} "
              f"{stats['expected_position']:<6.1f} {stats['champion_probability']:<8.1f} "
              f"{stats['top5_probability']:<8.1f} {stats['expected_points']:<8.1f} "
              f"{stats['points_range'][0]}-{stats['points_range'][1]}")
    
    print("-" * 100)
    print("\nNote: Predictions based on current Elo ratings and home advantage\n")

# --- Main Program ---
def main():
    team_ratings, match_history, match_counts = load_data(JSON_FILENAME)

    print("\n" + "="*70)
    print("ELO CHAMPIONSHIP RATING SYSTEM")
    print("="*70)

    while True:
        print("\n--- MENU ---")
        print("  1: Add Match Result")
        print("  2: Elo Rankings")
        print("  3: League Table")
        print("  4: Season Prediction")
        print("  5: Match History")
        print("  6: Undo Last Match")
        print("  7: Edit Match")
        print("  8: Delete Match")
        print("  9: Predict Match")
        print("  10: Backup & Restore")
        print("  11: Rename Team")
        print("  12: Reset All Data")
        print("  13: Save and Exit")

        choice = input("\nChoice: ").strip()

        if choice == '1':
            add_match_result(team_ratings, match_counts, match_history)
            create_backup(JSON_FILENAME)
            save_data(team_ratings, match_history, match_counts, JSON_FILENAME)
        elif choice == '2':
            display_rankings(team_ratings, match_counts)
        elif choice == '3':
            display_league_table(match_history, team_ratings)
        elif choice == '4':
            display_season_prediction(match_history, team_ratings)
        elif choice == '5':
            display_match_history(match_history, limit=20)
        elif choice == '6':
            undo_last_match(team_ratings, match_history, match_counts, JSON_FILENAME)
        elif choice == '7':
            edit_match(team_ratings, match_history, match_counts, JSON_FILENAME)
        elif choice == '8':
            delete_match(team_ratings, match_history, match_counts, JSON_FILENAME)
        elif choice == '9':
            if len(team_ratings) >= 2:
                predict_match(team_ratings, match_counts)
            else:
                print("Need at least 2 teams with ratings to predict.")
        elif choice == '10':
            should_reload = backup_and_restore_menu(JSON_FILENAME)
            if should_reload:
                team_ratings, match_history, match_counts = load_data(JSON_FILENAME)
        elif choice == '11':
            rename_team(team_ratings, match_history, match_counts, JSON_FILENAME)
        elif choice == '12':
            reset_championship(team_ratings, match_history, match_counts, JSON_FILENAME)
        elif choice == '13':
            create_backup(JSON_FILENAME)
            save_data(team_ratings, match_history, match_counts, JSON_FILENAME)
            print(f"\nData saved successfully.")
            print("Goodbye!")
            break
        else:
            print("Invalid choice.")

if __name__ == "__main__":
    main()
