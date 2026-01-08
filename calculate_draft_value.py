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
    print("DRAFT VALUE CALCULATOR")
    print("=" * 70)
    print()
    print("Draft Value = Player's Total VOR - Average of Next 2 at Position")
    print()
    
    # Load total values
    players = load_total_values('total_playoff_value.csv')
    print(f"Loaded {len(players)} players")
    
    # Calculate draft values
    players = calculate_draft_value(players)
    
    # Sort all players by draft value
    players.sort(key=lambda x: x['draft_value'], reverse=True)
    
    # Display top 50 by total VOR with draft value
    print("\n" + "=" * 90)
    print("TOP 50 PLAYERS BY TOTAL VOR (with Draft Value)")
    print("=" * 90)
    print(f"{'Rank':<5} {'Player':<25} {'Pos':<4} {'Team':<5} {'Total VOR':<10} {'Avg Next 2':<12} {'Draft Val':<10}")
    print("-" * 90)
    
    for p in players[:50]:
        print(f"{p['overall_rank']:<5} {p['name']:<25} {p['position']:<4} {p['team']:<5} "
              f"{p['total_vor']:<10.2f} {p['avg_next_two']:<12.2f} {p['draft_value']:<10.2f}")
    
    # Display by position
    positions = {'QB': [], 'RB': [], 'WR': [], 'TE': []}
    for p in players:
        if p['position'] in positions:
            positions[p['position']].append(p)
    
    # Sort each position by total_vor for ranking display
    for pos in positions:
        positions[pos].sort(key=lambda x: x['total_vor'], reverse=True)
    
    for pos_name, pos_players in positions.items():
        print(f"\n\n{'='*80}")
        print(f"TOP {pos_name}s BY TOTAL VOR (with Draft Value)")
        print("=" * 80)
        print(f"{'Pos Rank':<9} {'Player':<25} {'Team':<5} {'Total VOR':<10} {'Avg Next 2':<12} {'Draft Val':<10}")
        print("-" * 80)
        
        # Keep sorted by total_vor (already sorted)
        limit = 15 if pos_name in ['QB', 'TE'] else 25
        
        for p in pos_players[:limit]:
            print(f"{p['pos_rank']:<9} {p['name']:<25} {p['team']:<5} "
                  f"{p['total_vor']:<10.2f} {p['avg_next_two']:<12.2f} {p['draft_value']:<10.2f}")
    
    # Export to CSV (sorted by total_vor)
    output_file = 'draft_value.csv'
    
    # Keep sorted by total_vor
    players.sort(key=lambda x: x['total_vor'], reverse=True)
    
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'overall_rank', 'name', 'position', 'team', 'pos_rank', 'total_vor', 
            'total_points', 'avg_next_two', 'draft_value'
        ])
        writer.writeheader()
        writer.writerows(players)
    
    print(f"\n\n{'='*70}")
    print(f"EXPORTED: {output_file}")
    print("=" * 70)
    
    # Summary - who should you draft first?
    print("\n\nDRAFT PRIORITY (Biggest Value Drops):")
    print("-" * 60)
    
    top_by_dv = sorted(players, key=lambda x: x['draft_value'], reverse=True)[:15]
    for i, p in enumerate(top_by_dv, 1):
        print(f"  {i:>2}. {p['name']:<25} ({p['position']}) - {p['draft_value']:.2f} draft value")
    
    print("\n\nThis shows which players have the biggest drop-off to the next tier.")
    print("Higher draft value = more urgent to draft (bigger gap to alternatives)")
    
    return players


if __name__ == '__main__':
    main()

