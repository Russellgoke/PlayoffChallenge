import csv
import sys

sys.stdout.reconfigure(encoding='utf-8')

# Playoff weeks and their corresponding odds columns
PLAYOFF_WEEKS = {
    'Wild Card': {'filename': 'playoff_projections_wildcard.csv', 'odds_col': None},
    'Divisional': {'filename': 'playoff_projections_divisional.csv', 'odds_col': 'DIV APP'},
    'Conference': {'filename': 'playoff_projections_conference.csv', 'odds_col': 'Conf App'},
    'Super Bowl': {'filename': 'playoff_projections_superbowl.csv', 'odds_col': 'Conf Win'},
}

# Replacement value target ranks for each position slot
REPLACEMENT_RANKS = {
    'QB': 3,
    'TE': 8,
    'WR1': 8,
    'WR2': 8,
    'RB1': 8,
    'RB2': 8,
    'FLEX': 9
}


def load_team_odds(filename='teamodds.csv'):
    """Load team advancement odds from CSV file"""
    team_odds = {}
    
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
            for line in lines[1:]:  # Skip header
                parts = line.strip().split('\t')
                if len(parts) >= 2:
                    team = parts[0].strip()
                    
                    def parse_pct(s):
                        s = s.strip().replace('%', '')
                        try:
                            return float(s) / 100
                        except:
                            return 0.0
                    
                    # Parse the columns - handle spacing issues
                    # Format: Team | DIV APP  Conf App | Conf Win | SB Win
                    col1_parts = parts[1].split() if len(parts) > 1 else []
                    
                    div_app = parse_pct(col1_parts[0]) if col1_parts else 0
                    conf_app = parse_pct(col1_parts[1]) if len(col1_parts) > 1 else parse_pct(parts[2]) if len(parts) > 2 else 0
                    conf_win = parse_pct(parts[2]) if len(parts) > 2 and len(col1_parts) <= 1 else parse_pct(parts[3]) if len(parts) > 3 else 0
                    sb_win = parse_pct(parts[3]) if len(parts) > 3 and len(col1_parts) <= 1 else parse_pct(parts[4]) if len(parts) > 4 else 0
                    
                    # Fix parsing - try again with correct column positions
                    if len(parts) >= 5:
                        div_app = parse_pct(col1_parts[0]) if col1_parts else 0
                        conf_app = parse_pct(col1_parts[-1]) if len(col1_parts) > 1 else parse_pct(parts[2])
                        conf_win = parse_pct(parts[3])
                        sb_win = parse_pct(parts[4])
                    
                    team_odds[team] = {
                        'DIV APP': div_app,
                        'Conf App': conf_app,
                        'Conf Win': conf_win,
                        'SB Win': sb_win,
                    }
        
        print(f"Loaded odds for {len(team_odds)} teams:")
        for team, odds in team_odds.items():
            print(f"  {team}: DIV={odds['DIV APP']:.1%}, CONF={odds['Conf App']:.1%}, SB={odds['Conf Win']:.1%}")
        
        return team_odds
        
    except FileNotFoundError:
        print(f"Warning: {filename} not found.")
        return {}
    except Exception as e:
        print(f"Error loading team odds: {e}")
        return {}


def load_projections(filename):
    """Load player projections from CSV file"""
    players = []
    
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                players.append({
                    'name': row['name'],
                    'position': row['position'],
                    'team': row['team'],
                    'half_ppr_points': float(row['half_ppr_points']),
                })
        return players
    except FileNotFoundError:
        print(f"Warning: {filename} not found.")
        return []
    except Exception as e:
        print(f"Error loading {filename}: {e}")
        return []


def calculate_probability_weighted_baseline(players, position, target_rank, team_odds, odds_col):
    """
    Calculate the probability-weighted baseline for a position.
    
    Args:
        players: List of player dicts
        position: Position to filter (e.g., 'QB', 'RB', 'WR', 'TE') or 'FLEX' for RB/WR/TE
        target_rank: The target rank for replacement (e.g., 3 for 3rd best available)
        team_odds: Dict of team advancement odds
        odds_col: Column name for odds (e.g., 'DIV APP') or None for Wild Card (100%)
    
    Returns:
        Tuple of (baseline_points, baseline_player_name)
    """
    # Filter players by position
    if position == 'FLEX':
        filtered = [p for p in players if p['position'] in ['RB', 'WR', 'TE']]
    else:
        filtered = [p for p in players if p['position'] == position]
    
    # Sort by projected points (descending)
    filtered.sort(key=lambda x: x['half_ppr_points'], reverse=True)
    
    if not filtered:
        return 0, "N/A"
    
    # Calculate cumulative probability
    cumulative_prob = 0.0
    baseline_points = 0
    baseline_player = "N/A"
    
    for player in filtered:
        team = player['team']
        
        # Get team's probability of being in this round
        if odds_col is None:
            # Wild Card - all teams at 100%
            prob = 1.0
        else:
            prob = team_odds.get(team, {}).get(odds_col, 0.0)
        
        cumulative_prob += prob
        
        # When we reach the target rank, this is our baseline
        if cumulative_prob >= target_rank:
            baseline_points = player['half_ppr_points']
            baseline_player = player['name']
            break
    
    # If we didn't reach target rank, use the last player
    if baseline_points == 0 and filtered:
        baseline_points = filtered[-1]['half_ppr_points']
        baseline_player = filtered[-1]['name']
    
    return baseline_points, baseline_player


def calculate_all_baselines(players, team_odds, odds_col, round_name):
    """Calculate baselines for all position slots"""
    baselines = {}
    
    print(f"\n{'='*60}")
    print(f"REPLACEMENT VALUES - {round_name.upper()}")
    print(f"{'='*60}")
    
    # QB
    pts, name = calculate_probability_weighted_baseline(
        players, 'QB', REPLACEMENT_RANKS['QB'], team_odds, odds_col)
    baselines['QB'] = pts
    print(f"  QB  (rank {REPLACEMENT_RANKS['QB']}): {pts:6.2f} pts - {name}")
    
    # TE
    pts, name = calculate_probability_weighted_baseline(
        players, 'TE', REPLACEMENT_RANKS['TE'], team_odds, odds_col)
    baselines['TE'] = pts
    print(f"  TE  (rank {REPLACEMENT_RANKS['TE']}): {pts:6.2f} pts - {name}")
    
    # WR1
    pts, name = calculate_probability_weighted_baseline(
        players, 'WR', REPLACEMENT_RANKS['WR1'], team_odds, odds_col)
    baselines['WR1'] = pts
    print(f"  WR1 (rank {REPLACEMENT_RANKS['WR1']}): {pts:6.2f} pts - {name}")
    
    # WR2
    pts, name = calculate_probability_weighted_baseline(
        players, 'WR', REPLACEMENT_RANKS['WR2'], team_odds, odds_col)
    baselines['WR2'] = pts
    print(f"  WR2 (rank {REPLACEMENT_RANKS['WR2']}): {pts:6.2f} pts - {name}")
    
    # RB1
    pts, name = calculate_probability_weighted_baseline(
        players, 'RB', REPLACEMENT_RANKS['RB1'], team_odds, odds_col)
    baselines['RB1'] = pts
    print(f"  RB1 (rank {REPLACEMENT_RANKS['RB1']}): {pts:6.2f} pts - {name}")
    
    # RB2
    pts, name = calculate_probability_weighted_baseline(
        players, 'RB', REPLACEMENT_RANKS['RB2'], team_odds, odds_col)
    baselines['RB2'] = pts
    print(f"  RB2 (rank {REPLACEMENT_RANKS['RB2']}): {pts:6.2f} pts - {name}")
    
    # FLEX
    pts, name = calculate_probability_weighted_baseline(
        players, 'FLEX', REPLACEMENT_RANKS['FLEX'], team_odds, odds_col)
    baselines['FLEX'] = pts
    print(f"  FLEX (rank {REPLACEMENT_RANKS['FLEX']}): {pts:6.2f} pts - {name}")
    
    return baselines


def calculate_vor(players, baselines):
    """Calculate Value Over Replacement for each player"""
    for player in players:
        pos = player['position']
        pts = player['half_ppr_points']
        
        # Use the appropriate baseline
        if pos == 'QB':
            baseline = baselines['QB']
        elif pos == 'TE':
            baseline = baselines['TE']
        elif pos == 'WR':
            baseline = baselines['WR2']  # Use WR2 baseline for all WRs
        elif pos == 'RB':
            baseline = baselines['RB2']  # Use RB2 baseline for all RBs
        else:
            baseline = baselines['FLEX']
        
        player['vor'] = pts - baseline
    
    return players


def export_with_vor(players, baselines, filename):
    """Export players with VOR to CSV"""
    # Calculate VOR
    players = calculate_vor(players, baselines)
    
    # Sort by VOR
    players.sort(key=lambda x: x['vor'], reverse=True)
    
    output_file = filename.replace('.csv', '_vor.csv')
    
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['name', 'position', 'team', 'half_ppr_points', 'vor'])
        writer.writeheader()
        writer.writerows(players)
    
    print(f"\n  Exported VOR rankings to: {output_file}")
    return output_file


def main():
    print("=" * 60)
    print("PLAYOFF REPLACEMENT VALUE CALCULATOR")
    print("=" * 60)
    
    # Load team odds
    print("\nLoading team advancement odds...")
    team_odds = load_team_odds('teamodds.csv')
    
    if not team_odds:
        print("No team odds loaded. Using 100% for all teams.")
    
    all_baselines = {}
    
    # Process each playoff week
    for round_name, week_info in PLAYOFF_WEEKS.items():
        filename = week_info['filename']
        odds_col = week_info['odds_col']
        
        # Load projections
        players = load_projections(filename)
        
        if not players:
            print(f"\nSkipping {round_name} - no projections found")
            continue
        
        # Calculate baselines
        baselines = calculate_all_baselines(players, team_odds, odds_col, round_name)
        all_baselines[round_name] = baselines
        
        # Export with VOR
        export_with_vor(players.copy(), baselines, filename)
    
    # Summary comparison across weeks
    print("\n" + "=" * 60)
    print("BASELINE COMPARISON ACROSS WEEKS")
    print("=" * 60)
    print(f"\n{'Position':<8}", end='')
    for round_name in PLAYOFF_WEEKS.keys():
        print(f"{round_name:<14}", end='')
    print()
    print("-" * 70)
    
    for pos in ['QB', 'TE', 'WR1', 'WR2', 'RB1', 'RB2', 'FLEX']:
        print(f"{pos:<8}", end='')
        for round_name in PLAYOFF_WEEKS.keys():
            if round_name in all_baselines:
                pts = all_baselines[round_name].get(pos, 0)
                print(f"{pts:<14.2f}", end='')
            else:
                print(f"{'N/A':<14}", end='')
        print()
    
    print("\n" + "=" * 60)
    print("VOR FILES GENERATED:")
    print("=" * 60)
    for week_info in PLAYOFF_WEEKS.values():
        vor_file = week_info['filename'].replace('.csv', '_vor.csv')
        print(f"  - {vor_file}")
    
    return all_baselines


if __name__ == '__main__':
    main()

