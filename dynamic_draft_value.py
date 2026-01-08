import csv
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')


def load_total_values(filename='total_playoff_value.csv'):
    """Load total playoff values from CSV"""
    players = []
    
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                players.append({
                    'name': row['name'],
                    'position': row['position'],
                    'team': row['team'],
                    'total_vor': float(row['total_vor']),
                    'total_points': float(row['total_points']),
                })
        return players
    except Exception as e:
        print(f"Error loading {filename}: {e}")
        return []


def load_drafted_players(filename='players_drafted.txt'):
    """Load list of drafted players from text file"""
    drafted = []
    
    try:
        with open(filename, 'r', encoding='utf-8-sig') as f:  # utf-8-sig handles BOM
            content = f.read()
            # Split by comma or newline and strip whitespace
            names = []
            for line in content.replace(',', '\n').split('\n'):
                name = line.strip()
                if name:
                    names.append(name)
            drafted = names
        return drafted
    except FileNotFoundError:
        print(f"Note: {filename} not found. Starting with empty draft.")
        return []
    except Exception as e:
        print(f"Error loading {filename}: {e}")
        return []


def find_similar_names(name, all_names, max_suggestions=3):
    """Find similar player names using fuzzy matching"""
    name_lower = name.lower()
    scores = {}
    
    for player_name in all_names:
        player_lower = player_name.lower()
        score = 0
        
        # Check if any part of the name matches
        name_parts = name_lower.split()
        player_parts = player_lower.split()
        
        for part in name_parts:
            # Exact substring match (highest priority)
            if part in player_lower:
                score += 10 if len(part) >= 3 else 8
            
            # Check each player name part
            for ppart in player_parts:
                # Exact part match
                if part == ppart:
                    score += 15
                # Check for starting with same letters
                elif len(part) >= 2 and ppart.startswith(part[:min(3, len(part))]):
                    score += 5
                # Check for similar length and shared characters
                if len(ppart) >= 2 and abs(len(part) - len(ppart)) <= 2:
                    shared = sum(1 for c in part if c in ppart)
                    if shared >= len(part) * 0.6:
                        score += 3
                # Short name exact match (like "Bo")
                if len(part) == 2 and part == ppart:
                    score += 20
        
        if score > 0:
            scores[player_name] = score
    
    # Sort by score and return top suggestions
    sorted_names = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
    return sorted_names[:max_suggestions]


def validate_drafted_players(drafted_names, all_players):
    """Validate that all drafted player names exist in the player pool"""
    all_player_names = {p['name'] for p in all_players}
    
    errors = []
    for name in drafted_names:
        if name not in all_player_names:
            # Try to find similar names for suggestion
            similar = find_similar_names(name, all_player_names)
            if similar:
                errors.append(f"  '{name}' not found. Did you mean: {', '.join(similar)}?")
            else:
                errors.append(f"  '{name}' not found. Check spelling.")
    
    if errors:
        print("\n" + "=" * 60)
        print("ERROR: Invalid player names in players_drafted.txt")
        print("=" * 60)
        for err in errors:
            print(err)
        print("\nPlease fix the player names and try again.")
        sys.exit(1)
    
    return True


def calculate_draft_value(players):
    """
    Calculate draft value for each player.
    Draft Value = Player's Total VOR - Average of next 2 players' Total VOR at SAME POSITION
    """
    # Group players by position
    by_position = defaultdict(list)
    for p in players:
        by_position[p['position']].append(p)
    
    # Sort each position by total_vor and calculate draft value within position
    for pos, pos_players in by_position.items():
        pos_players.sort(key=lambda x: x['total_vor'], reverse=True)
        
        for i, player in enumerate(pos_players):
            # Get next 2 players at SAME position
            next_players = pos_players[i+1:i+3]
            
            if len(next_players) >= 2:
                avg_next_two = (next_players[0]['total_vor'] + next_players[1]['total_vor']) / 2
            elif len(next_players) == 1:
                avg_next_two = next_players[0]['total_vor']
            else:
                # Last player at position - use 0 as baseline
                avg_next_two = 0
            
            player['draft_value'] = player['total_vor'] - avg_next_two
            player['avg_next_two'] = avg_next_two
            player['pos_rank'] = i + 1
    
    # Sort all players by total_vor for overall ranking
    players.sort(key=lambda x: x['total_vor'], reverse=True)
    for i, player in enumerate(players):
        player['overall_rank'] = i + 1
    
    return players


def main():
    print("=" * 70)
    print("DYNAMIC DRAFT VALUE CALCULATOR")
    print("=" * 70)
    
    # Load all players
    all_players = load_total_values('total_playoff_value.csv')
    print(f"\nLoaded {len(all_players)} total players")
    
    # Load drafted players
    drafted_names = load_drafted_players('players_drafted.txt')
    
    if drafted_names:
        print(f"\nDrafted players ({len(drafted_names)}):")
        for name in drafted_names:
            print(f"  - {name}")
        
        # Validate all names exist
        validate_drafted_players(drafted_names, all_players)
        
        # Remove drafted players
        available_players = [p for p in all_players if p['name'] not in drafted_names]
        print(f"\nRemaining available players: {len(available_players)}")
    else:
        print("\nNo players drafted yet.")
        available_players = all_players
    
    # Calculate draft values for available players
    available_players = calculate_draft_value(available_players)
    
    # Display results
    print("\n" + "=" * 90)
    print("TOP 30 AVAILABLE PLAYERS BY TOTAL VOR")
    print("=" * 90)
    print(f"{'Rank':<5} {'Player':<25} {'Pos':<4} {'Team':<5} {'Total VOR':<10} {'Avg Next 2':<12} {'Draft Val':<10}")
    print("-" * 90)
    
    for p in available_players[:30]:
        print(f"{p['overall_rank']:<5} {p['name']:<25} {p['position']:<4} {p['team']:<5} "
              f"{p['total_vor']:<10.2f} {p['avg_next_two']:<12.2f} {p['draft_value']:<10.2f}")
    
    # Display by position
    positions = {'QB': [], 'RB': [], 'WR': [], 'TE': []}
    for p in available_players:
        if p['position'] in positions:
            positions[p['position']].append(p)
    
    for pos_name, pos_players in positions.items():
        print(f"\n\n{'='*80}")
        print(f"TOP AVAILABLE {pos_name}s")
        print("=" * 80)
        print(f"{'Pos Rank':<9} {'Player':<25} {'Team':<5} {'Total VOR':<10} {'Avg Next 2':<12} {'Draft Val':<10}")
        print("-" * 80)
        
        limit = 10 if pos_name in ['QB', 'TE'] else 15
        
        for p in pos_players[:limit]:
            print(f"{p['pos_rank']:<9} {p['name']:<25} {p['team']:<5} "
                  f"{p['total_vor']:<10.2f} {p['avg_next_two']:<12.2f} {p['draft_value']:<10.2f}")
    
    # Draft recommendations
    print("\n\n" + "=" * 70)
    print("DRAFT RECOMMENDATIONS (Biggest Value Drops)")
    print("=" * 70)
    
    # Sort by draft value
    by_draft_value = sorted(available_players, key=lambda x: x['draft_value'], reverse=True)
    
    print("\nTop picks by urgency (highest draft value):")
    for i, p in enumerate(by_draft_value[:10], 1):
        print(f"  {i:>2}. {p['name']:<25} ({p['position']}) - {p['draft_value']:.2f} DV, {p['total_vor']:.2f} VOR")
    
    # Best available by position
    print("\n\nBest available by position:")
    for pos_name in ['QB', 'RB', 'WR', 'TE']:
        if positions[pos_name]:
            best = positions[pos_name][0]
            print(f"  {pos_name}: {best['name']:<25} - {best['total_vor']:.2f} VOR, {best['draft_value']:.2f} DV")
    
    # Export to CSV (only available players, sorted by total_vor)
    output_file = 'draft_value.csv'
    available_players.sort(key=lambda x: x['total_vor'], reverse=True)
    
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'overall_rank', 'name', 'position', 'team', 'pos_rank', 'total_vor', 
            'total_points', 'avg_next_two', 'draft_value'
        ])
        writer.writeheader()
        writer.writerows(available_players)
    
    print(f"\n\nExported {len(available_players)} available players to: {output_file}")
    
    return available_players


if __name__ == '__main__':
    main()

