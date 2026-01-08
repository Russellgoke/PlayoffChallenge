import csv
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')

# Import shared utilities
from utils import (
    load_team_odds,
    load_vor_file,
)

# Playoff weeks and their VOR files with corresponding odds column
PLAYOFF_WEEKS = [
    {'name': 'Wild Card', 'vor_file': 'playoff_projections_wildcard_vor.csv', 'odds_col': None},
    {'name': 'Divisional', 'vor_file': 'playoff_projections_divisional_vor.csv', 'odds_col': 'DIV APP'},
    {'name': 'Conference', 'vor_file': 'playoff_projections_conference_vor.csv', 'odds_col': 'Conf App'},
    {'name': 'Super Bowl', 'vor_file': 'playoff_projections_superbowl_vor.csv', 'odds_col': 'Conf Win'},
]




def calculate_total_value(team_odds):
    """Calculate total playoff value for each player weighted by play probability"""
    
    # Dictionary to accumulate player values
    player_totals = defaultdict(lambda: {
        'position': '',
        'team': '',
        'weekly_vor': {},
        'weekly_prob': {},
        'total_vor': 0,
        'total_points': 0,
    })
    
    print("Loading VOR data for each week...")
    
    for week_info in PLAYOFF_WEEKS:
        week_name = week_info['name']
        vor_file = week_info['vor_file']
        odds_col = week_info['odds_col']
        
        players = load_vor_file(vor_file)
        print(f"  {week_name}: {len(players)} players")
        
        for name, data in players.items():
            team = data['team']
            vor = data['vor']
            pts = data['half_ppr_points']
            
            # Skip players whose teams aren't in the playoffs
            if team not in team_odds:
                continue
            
            # Get probability of playing this week
            if odds_col is None:
                # Wild Card - all playoff teams play (100%)
                prob = 1.0
            else:
                prob = team_odds.get(team, {}).get(odds_col, 0.0)
            
            # Store player info
            player_totals[name]['position'] = data['position']
            player_totals[name]['team'] = team
            player_totals[name]['weekly_vor'][week_name] = vor
            player_totals[name]['weekly_prob'][week_name] = prob
            player_totals[name]['weekly_pts'] = player_totals[name].get('weekly_pts', {})
            player_totals[name]['weekly_pts'][week_name] = pts
            
            # Add weighted VOR to total (use max(0, vor) - you wouldn't start a negative VOR player)
            effective_vor = max(0, vor)
            weighted_vor = effective_vor * prob
            player_totals[name]['total_vor'] += weighted_vor
            
            # Also track weighted total points (using effective VOR logic)
            # If VOR is negative, player wouldn't be started, so use 0 contribution
            if vor > 0:
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
    print("Formula: Total Value = SUM(Week VOR × Probability of Playing That Week)")
    print()
    
    # Load team odds
    print("Loading team advancement odds...")
    team_odds = load_team_odds('teamodds.csv')
    print(f"  Loaded odds for {len(team_odds)} teams")
    print()
    
    # Calculate total values
    player_totals = calculate_total_value(team_odds)
    print(f"\nCalculated totals for {len(player_totals)} players")
    
    # Convert to list and sort by total VOR
    players_list = []
    for name, data in player_totals.items():
        players_list.append({
            'name': name,
            'position': data['position'],
            'team': data['team'],
            'total_vor': round(data['total_vor'], 2),
            'total_points': round(data['total_points'], 2),
            'wc_vor': round(data['weekly_vor'].get('Wild Card', 0), 2),
            'div_vor': round(data['weekly_vor'].get('Divisional', 0), 2),
            'conf_vor': round(data['weekly_vor'].get('Conference', 0), 2),
            'sb_vor': round(data['weekly_vor'].get('Super Bowl', 0), 2),
            'wc_prob': data['weekly_prob'].get('Wild Card', 0),
            'div_prob': data['weekly_prob'].get('Divisional', 0),
            'conf_prob': data['weekly_prob'].get('Conference', 0),
            'sb_prob': data['weekly_prob'].get('Super Bowl', 0),
        })
    
    # Sort by total VOR (descending)
    players_list.sort(key=lambda x: x['total_vor'], reverse=True)
    
    # Display top players overall
    print("\n" + "=" * 90)
    print("TOP 50 PLAYERS BY TOTAL PLAYOFF VALUE")
    print("=" * 90)
    print(f"{'Rank':<5} {'Player':<25} {'Pos':<4} {'Team':<5} {'Total VOR':<10} {'WC':<8} {'DIV':<8} {'CONF':<8} {'SB':<8}")
    print("-" * 90)
    
    for i, p in enumerate(players_list[:50], 1):
        # Show weighted contributions (clamped to 0 - you wouldn't start negative VOR players)
        wc_contrib = max(0, p['wc_vor']) * p['wc_prob']
        div_contrib = max(0, p['div_vor']) * p['div_prob']
        conf_contrib = max(0, p['conf_vor']) * p['conf_prob']
        sb_contrib = max(0, p['sb_vor']) * p['sb_prob']
        
        print(f"{i:<5} {p['name']:<25} {p['position']:<4} {p['team']:<5} {p['total_vor']:<10.2f} "
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
        print(f"{'Rank':<5} {'Player':<25} {'Team':<5} {'Total VOR':<10} {'Prob Adj Pts':<12}")
        print("-" * 70)
        
        limit = 20 if pos_name == 'QB' else 30 if pos_name in ['RB', 'WR'] else 15
        for i, p in enumerate(pos_players[:limit], 1):
            print(f"{i:<5} {p['name']:<25} {p['team']:<5} {p['total_vor']:<10.2f} {p['total_points']:<12.2f}")
    
    # Export to CSV
    output_file = 'total_playoff_value.csv'
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'name', 'position', 'team', 'total_vor', 'total_points',
            'wc_vor', 'div_vor', 'conf_vor', 'sb_vor',
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
        print(f"  {i}. {p['name']} ({p['position']}, {p['team']}) - {p['total_vor']:.2f} Total VOR")
    
    return players_list


if __name__ == '__main__':
    main()
