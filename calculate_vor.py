import csv
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')

# Import shared utilities
from utils import (
    load_team_odds,
    load_projections,
    load_my_team,
    get_team_play_probability,
)

# Import VOT functions
from calculate_vot import (
    get_my_team_players_by_position,
    calculate_vot_for_player,
)

# Playoff weeks and their corresponding odds columns
PLAYOFF_WEEKS = {
    'Wild Card': {'filename': 'playoff_projections_wildcard.csv', 'odds_col': None},
    'Divisional': {'filename': 'playoff_projections_divisional.csv', 'odds_col': 'DIV APP'},
    'Conference': {'filename': 'playoff_projections_conference.csv', 'odds_col': 'Conf App'},
    'Super Bowl': {'filename': 'playoff_projections_superbowl.csv', 'odds_col': 'Conf Win'},
}

# Replacement value target ranks for each position slot
REPLACEMENT_RANKS = {
    'QB': 5,
    'TE': 10,
    'WR1': 10,
    'WR2': 10,
    'RB1': 10,
    'RB2': 10,
    'FLEX': 15
}




def calculate_probability_weighted_baseline(players, position, target_rank, team_odds, odds_col, use_vot=False):
    """
    Calculate the probability-weighted baseline for a position.
    
    Args:
        players: List of player dicts (must have 'vot' field if use_vot=True)
        position: Position to filter (e.g., 'QB', 'RB', 'WR', 'TE') or 'FLEX' for RB/WR/TE
        target_rank: The target rank for replacement (e.g., 3 for 3rd best available)
        team_odds: Dict of team advancement odds
        odds_col: Column name for odds (e.g., 'DIV APP') or None for Wild Card (100%)
        use_vot: If True, use VOT for baseline instead of raw points
    
    Returns:
        Tuple of (baseline_value, baseline_player_name)
    """
    # Filter players by position
    if position == 'FLEX':
        filtered = [p for p in players if p['position'] in ['RB', 'WR', 'TE']]
    else:
        filtered = [p for p in players if p['position'] == position]
    
    # Determine which field to use for sorting and baseline
    value_field = 'vot' if use_vot else 'half_ppr_points'
    
    # Sort by value (descending)
    filtered.sort(key=lambda x: x.get(value_field, 0), reverse=True)
    
    if not filtered:
        return 0, "N/A"
    
    # Calculate cumulative probability
    cumulative_prob = 0.0
    baseline_value = 0
    baseline_player = "N/A"
    
    for player in filtered:
        team = player['team']
        
        # Get team's probability of being in this round
        prob = get_team_play_probability(team, team_odds, odds_col)
        
        cumulative_prob += prob
        
        # When we reach the target rank, this is our baseline
        if cumulative_prob >= target_rank:
            baseline_value = player.get(value_field, 0)
            baseline_player = player['name']
            break
    
    # If we didn't reach target rank, use the last player
    if baseline_value == 0 and filtered:
        baseline_value = filtered[-1].get(value_field, 0)
        baseline_player = filtered[-1]['name']
    
    return baseline_value, baseline_player


def calculate_all_baselines(players, team_odds, odds_col, round_name, use_vot=False):
    """Calculate baselines for all position slots"""
    baselines = {}
    
    baseline_type = "VOT" if use_vot else "POINTS"
    print(f"\n{'='*60}")
    print(f"REPLACEMENT VALUES ({baseline_type}) - {round_name.upper()}")
    print(f"{'='*60}")
    
    unit = "VOT" if use_vot else "pts"
    
    # QB
    val, name = calculate_probability_weighted_baseline(
        players, 'QB', REPLACEMENT_RANKS['QB'], team_odds, odds_col, use_vot)
    baselines['QB'] = val
    print(f"  QB  (rank {REPLACEMENT_RANKS['QB']}): {val:6.2f} {unit} - {name}")
    
    # TE
    val, name = calculate_probability_weighted_baseline(
        players, 'TE', REPLACEMENT_RANKS['TE'], team_odds, odds_col, use_vot)
    baselines['TE'] = val
    print(f"  TE  (rank {REPLACEMENT_RANKS['TE']}): {val:6.2f} {unit} - {name}")
    
    # WR1
    val, name = calculate_probability_weighted_baseline(
        players, 'WR', REPLACEMENT_RANKS['WR1'], team_odds, odds_col, use_vot)
    baselines['WR1'] = val
    print(f"  WR1 (rank {REPLACEMENT_RANKS['WR1']}): {val:6.2f} {unit} - {name}")
    
    # WR2
    val, name = calculate_probability_weighted_baseline(
        players, 'WR', REPLACEMENT_RANKS['WR2'], team_odds, odds_col, use_vot)
    baselines['WR2'] = val
    print(f"  WR2 (rank {REPLACEMENT_RANKS['WR2']}): {val:6.2f} {unit} - {name}")
    
    # RB1
    val, name = calculate_probability_weighted_baseline(
        players, 'RB', REPLACEMENT_RANKS['RB1'], team_odds, odds_col, use_vot)
    baselines['RB1'] = val
    print(f"  RB1 (rank {REPLACEMENT_RANKS['RB1']}): {val:6.2f} {unit} - {name}")
    
    # RB2
    val, name = calculate_probability_weighted_baseline(
        players, 'RB', REPLACEMENT_RANKS['RB2'], team_odds, odds_col, use_vot)
    baselines['RB2'] = val
    print(f"  RB2 (rank {REPLACEMENT_RANKS['RB2']}): {val:6.2f} {unit} - {name}")
    
    # FLEX
    val, name = calculate_probability_weighted_baseline(
        players, 'FLEX', REPLACEMENT_RANKS['FLEX'], team_odds, odds_col, use_vot)
    baselines['FLEX'] = val
    print(f"  FLEX (rank {REPLACEMENT_RANKS['FLEX']}): {val:6.2f} {unit} - {name}")
    
    return baselines


def calculate_vor(players, baselines, use_vot=False):
    """
    Calculate Value Over Replacement for each player.
    
    If use_vot=True, calculates VOR based on VOT values (requires 'vot' field).
    This means VOR = player's VOT - replacement-level VOT.
    """
    for player in players:
        pos = player['position']
        
        # Use VOT if available and requested, otherwise use raw points
        if use_vot and 'vot' in player:
            value = player['vot']
        else:
            value = player['half_ppr_points']
        
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
        
        player['vor'] = value - baseline
    
    return players


def export_with_vor(players, baselines, filename, my_team_names=None, my_team_by_position=None, team_odds=None, odds_col=None):
    """
    Export players with VOR and VOT to CSV.
    
    Flow when my_team is provided:
    1. Calculate VOT first (value over your team)
    2. Calculate VOT baselines (replacement-level VOT)
    3. Calculate VOR = VOT - VOT baseline
    
    Flow when no my_team:
    1. Calculate VOR = raw points - points baseline
    """
    has_vot = my_team_names and my_team_by_position is not None
    
    if has_vot:
        # Step 1: Calculate VOT for all players first
        for player in players:
            player['vot'] = calculate_vot_for_player(player, my_team_by_position, team_odds, odds_col)
            player['play_prob'] = get_team_play_probability(player['team'], team_odds, odds_col)
            player['on_my_team'] = 1 if player['name'] in my_team_names else 0
        
        # Step 2: Calculate VOT baselines (replacement-level VOT at each position)
        vot_baselines = calculate_all_baselines(players, team_odds, odds_col, 
                                                 f"{filename.split('_')[2].replace('.csv','')} VOT", 
                                                 use_vot=True)
        
        # Step 3: Calculate VOR using VOT values
        players = calculate_vor(players, vot_baselines, use_vot=True)
    else:
        # No team provided - use raw points for VOR
        players = calculate_vor(players, baselines, use_vot=False)
    
    # Sort by VOR
    players.sort(key=lambda x: x['vor'], reverse=True)
    
    output_file = filename.replace('.csv', '_vor.csv')
    
    # Determine fieldnames based on whether we have VOT
    if has_vot:
        fieldnames = ['name', 'position', 'team', 'half_ppr_points', 'play_prob', 'vot', 'vor', 'on_my_team']
    else:
        fieldnames = ['name', 'position', 'team', 'half_ppr_points', 'vor']
    
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        for p in players:
            row = {k: p.get(k, '') for k in fieldnames}
            # Round numeric values
            if 'play_prob' in row and row['play_prob'] != '':
                row['play_prob'] = round(row['play_prob'], 3)
            if 'vor' in row and row['vor'] != '':
                row['vor'] = round(row['vor'], 2)
            if 'vot' in row and row['vot'] != '':
                row['vot'] = round(row['vot'], 2)
            writer.writerow(row)
    
    print(f"\n  Exported rankings to: {output_file}")
    return output_file


def main():
    print("=" * 60)
    print("PLAYOFF REPLACEMENT VALUE CALCULATOR")
    print("=" * 60)
    
    # Load team odds
    print("\nLoading team advancement odds...")
    team_odds = load_team_odds('teamodds.csv', verbose=True)
    
    if not team_odds:
        print("No team odds loaded. Using 100% for all teams.")
    
    # Load my team for VOT calculations
    my_team_names = load_my_team('my_team.txt')
    if my_team_names:
        print(f"\nLoaded my team ({len(my_team_names)} players):")
        for name in my_team_names:
            print(f"  - {name}")
    else:
        print("\nNo my_team.txt found - VOT will not be calculated.")
        print("Create my_team.txt with your drafted players to enable VOT.")
    
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
        
        # Get my team players by position (for VOT calculation)
        my_team_by_position = None
        if my_team_names:
            my_team_by_position = get_my_team_players_by_position(my_team_names, players, team_odds, odds_col)
            
            # Print my team by position
            print(f"\n  My Team for {round_name}:")
            for pos in ['QB', 'RB', 'WR', 'TE']:
                pos_players = my_team_by_position.get(pos, [])
                if pos_players:
                    print(f"    {pos}:")
                    for p in pos_players:
                        print(f"      {p['name']:<25} - {p['half_ppr_points']:.2f} pts ({p['play_prob']:.1%})")
        
        # Export with VOR (and VOT if my team is loaded)
        export_with_vor(players.copy(), baselines, filename, 
                        my_team_names, my_team_by_position, team_odds, odds_col)
    
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

