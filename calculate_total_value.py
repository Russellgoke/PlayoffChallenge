import csv
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')

# Import shared utilities
from utils import (
    load_team_odds,
    load_vot_file,
    get_output_path,
)

# Import calculate_vot to run it directly
import calculate_vot

# Playoff weeks and their VOT files with corresponding odds column
PLAYOFF_WEEKS = [
    {'name': 'Wild Card', 'vot_file': 'playoff_projections_wildcard_vot.csv', 'odds_col': 'Wild Card Appearance'},
    {'name': 'Divisional', 'vot_file': 'playoff_projections_divisional_vot.csv', 'odds_col': 'DIV APP'},
    {'name': 'Conference', 'vot_file': 'playoff_projections_conference_vot.csv', 'odds_col': 'Conf App'},
    {'name': 'Super Bowl', 'vot_file': 'playoff_projections_superbowl_vot.csv', 'odds_col': 'Conf Win'},
]




def calculate_total_value(team_odds):
    """Calculate total playoff value for each player using VOT (Value Over Team)"""
    
    # Dictionary to accumulate player values
    player_totals = defaultdict(lambda: {
        'position': '',
        'team': '',
        'weekly_vot': {},
        'weekly_prob': {},
        'total_vot': 0,
        'total_points': 0,
    })
    
    print("Loading VOT data for each week...")
    
    for week_info in PLAYOFF_WEEKS:
        week_name = week_info['name']
        vot_file = week_info['vot_file']
        odds_col = week_info['odds_col']
        
        players = load_vot_file(vot_file)
        print(f"  {week_name}: {len(players)} players")
        
        for name, data in players.items():
            team = data['team']
            vot = data['vot']
            pts = data['half_ppr_points']
            
            # Skip players whose teams aren't in the playoffs
            if team not in team_odds:
                continue
            
            # Get probability of playing this week
            prob = team_odds.get(team, {}).get(odds_col, 0.0)
            
            # Store player info
            player_totals[name]['position'] = data['position']
            player_totals[name]['team'] = team
            player_totals[name]['weekly_vot'][week_name] = vot
            player_totals[name]['weekly_prob'][week_name] = prob
            player_totals[name]['weekly_pts'] = player_totals[name].get('weekly_pts', {})
            player_totals[name]['weekly_pts'][week_name] = pts
            
            # Add VOT to total (use max(0, vot) - you wouldn't start a negative VOT player)
            # NOTE: VOT already includes play probability, so don't multiply by prob again
            effective_vot = max(0, vot)
            player_totals[name]['total_vot'] += effective_vot
            
            # Track weighted total points (raw points * probability)
            # If VOT is negative, player wouldn't be started, so use 0 contribution
            if vot > 0:
                weighted_pts = pts * prob
            else:
                weighted_pts = 0
            player_totals[name]['total_points'] += weighted_pts
    
    return dict(player_totals)


def main():
    print("=" * 70)
    print("TOTAL PLAYOFF VALUE CALCULATOR")
    print("=" * 70)
    print()
    print("Formula: Total Value = SUM(Weekly VOT)")
    print("VOT = Value Over Team (marginal lineup value with baseline fill-in)")
    print()
    
    # Always run calculate_vot first to get fresh VOT data
    print("Running VOT calculations...")
    calculate_vot.main()
    print("\n" + "=" * 70)
    print("CALCULATING TOTAL PLAYOFF VALUE")
    print("=" * 70 + "\n")
    
    # Load team odds
    print("Loading team advancement odds...")
    team_odds = load_team_odds('teamodds.csv')
    print(f"  Loaded odds for {len(team_odds)} teams")
    print()
    
    # Calculate total values
    player_totals = calculate_total_value(team_odds)
    print(f"\nCalculated totals for {len(player_totals)} players")
    
    # Convert to list and sort by total VOT
    players_list = []
    for name, data in player_totals.items():
        players_list.append({
            'name': name,
            'position': data['position'],
            'team': data['team'],
            'total_vot': round(data['total_vot'], 2),
            'total_points': round(data['total_points'], 2),
            'wc_vot': round(data['weekly_vot'].get('Wild Card', 0), 2),
            'div_vot': round(data['weekly_vot'].get('Divisional', 0), 2),
            'conf_vot': round(data['weekly_vot'].get('Conference', 0), 2),
            'sb_vot': round(data['weekly_vot'].get('Super Bowl', 0), 2),
            'wc_prob': data['weekly_prob'].get('Wild Card', 0),
            'div_prob': data['weekly_prob'].get('Divisional', 0),
            'conf_prob': data['weekly_prob'].get('Conference', 0),
            'sb_prob': data['weekly_prob'].get('Super Bowl', 0),
        })
    
    # Sort by total VOT (descending)
    players_list.sort(key=lambda x: x['total_vot'], reverse=True)
    
    # Display top players overall
    print("\n" + "=" * 90)
    print("TOP 50 PLAYERS BY TOTAL PLAYOFF VALUE (VOT)")
    print("=" * 90)
    print(f"{'Rank':<5} {'Player':<25} {'Pos':<4} {'Team':<5} {'Total VOT':<10} {'WC':<8} {'DIV':<8} {'CONF':<8} {'SB':<8}")
    print("-" * 90)
    
    for i, p in enumerate(players_list[:50], 1):
        # Show VOT contributions (already probability-weighted, clamped to 0)
        wc_contrib = max(0, p['wc_vot'])
        div_contrib = max(0, p['div_vot'])
        conf_contrib = max(0, p['conf_vot'])
        sb_contrib = max(0, p['sb_vot'])
        
        print(f"{i:<5} {p['name']:<25} {p['position']:<4} {p['team']:<5} {p['total_vot']:<10.2f} "
              f"{wc_contrib:<8.2f} {div_contrib:<8.2f} {conf_contrib:<8.2f} {sb_contrib:<8.2f}")
    
    # Display by position
    positions = {'QB': [], 'RB': [], 'WR': [], 'TE': []}
    for p in players_list:
        if p['position'] in positions:
            positions[p['position']].append(p)
    
    for pos_name, pos_players in positions.items():
        print(f"\n\n{'='*70}")
        print(f"TOP {pos_name}s BY TOTAL PLAYOFF VALUE")
        print("=" * 70)
        print(f"{'Rank':<5} {'Player':<25} {'Team':<5} {'Total VOT':<10} {'Prob Adj Pts':<12}")
        print("-" * 70)
        
        limit = 20 if pos_name == 'QB' else 30 if pos_name in ['RB', 'WR'] else 15
        for i, p in enumerate(pos_players[:limit], 1):
            print(f"{i:<5} {p['name']:<25} {p['team']:<5} {p['total_vot']:<10.2f} {p['total_points']:<12.2f}")
    
    # Export to CSV
    output_file = get_output_path('total_playoff_value.csv')
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'name', 'position', 'team', 'total_vot', 'total_points',
            'wc_vot', 'div_vot', 'conf_vot', 'sb_vot',
            'wc_prob', 'div_prob', 'conf_prob', 'sb_prob'
        ])
        writer.writeheader()
        writer.writerows(players_list)
    
    print(f"\n\n{'='*70}")
    print(f"EXPORTED: {output_file}")
    print("=" * 70)
    print(f"Total players ranked: {len(players_list)}")
    
    # Summary stats
    print("\n\nTOP 10 MOST VALUABLE PLAYERS:")
    print("-" * 50)
    for i, p in enumerate(players_list[:10], 1):
        print(f"  {i}. {p['name']} ({p['position']}, {p['team']}) - {p['total_vot']:.2f} Total VOT")
    
    return players_list


if __name__ == '__main__':
    main()
