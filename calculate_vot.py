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
    get_output_path,
    ensure_projections_exist,
)

# Playoff weeks and their corresponding odds columns
PLAYOFF_WEEKS = {
    'Wild Card': {'filename': 'playoff_projections_wildcard.csv', 'odds_col': None},
    'Divisional': {'filename': 'playoff_projections_divisional.csv', 'odds_col': 'DIV APP'},
    'Conference': {'filename': 'playoff_projections_conference.csv', 'odds_col': 'Conf App'},
    'Super Bowl': {'filename': 'playoff_projections_superbowl.csv', 'odds_col': 'Conf Win'},
}

# Roster slots
ROSTER_SLOTS = {
    'QB': 1,
    'RB': 2,
    'WR': 2,
    'TE': 1,
    'FLEX': 1,  # RB/WR/TE eligible
}




def get_my_team_players_by_position(my_team_names, players, team_odds, odds_col):
    """
    Get all my team's players grouped by position, sorted by projected points.
    Returns dict of position -> list of player dicts with expected values.
    
    Note: Players are sorted by raw projected points (for determining starters),
    but expected_points is still calculated for VOT calculations.
    """
    # Get my team's players from the projection data
    my_players = []
    for p in players:
        if p['name'] in my_team_names:
            p_copy = p.copy()
            p_copy['play_prob'] = get_team_play_probability(p['team'], team_odds, odds_col)
            p_copy['expected_points'] = p['half_ppr_points'] * p_copy['play_prob']
            my_players.append(p_copy)
    
    # Group by position
    by_position = defaultdict(list)
    for p in my_players:
        by_position[p['position']].append(p)
    
    # Sort each position by projected points (descending) - for determining starters
    for pos in by_position:
        by_position[pos].sort(key=lambda x: x['half_ppr_points'], reverse=True)
    
    return by_position


def calculate_availability_probs(players):
    """
    Calculate probability distribution for how many players are available.
    
    Args:
        players: List of player dicts with 'play_prob' key
    
    Returns:
        Tuple of (prob_0_available, prob_1_available, prob_2_available)
    """
    if not players:
        return (1.0, 0.0, 0.0)
    
    n = len(players)
    
    # P(0 available) = product of (1 - play_prob) for all players
    prob_0 = 1.0
    for p in players:
        prob_0 *= (1 - p['play_prob'])
    
    # P(1 available) = sum over each player of:
    #   (that player's play_prob) * (all others eliminated)
    prob_1 = 0.0
    for i, p in enumerate(players):
        prob_this_plays = p['play_prob']
        prob_others_eliminated = 1.0
        for j, other_p in enumerate(players):
            if i != j:
                prob_others_eliminated *= (1 - other_p['play_prob'])
        prob_1 += prob_this_plays * prob_others_eliminated
    
    # P(2 available) = sum over all pairs of players of:
    #   (both play) * (all others eliminated)
    prob_2 = 0.0
    if n >= 2:
        for i in range(n):
            for j in range(i + 1, n):
                prob_both_play = players[i]['play_prob'] * players[j]['play_prob']
                prob_others_eliminated = 1.0
                for k, other_p in enumerate(players):
                    if k != i and k != j:
                        prob_others_eliminated *= (1 - other_p['play_prob'])
                prob_2 += prob_both_play * prob_others_eliminated
    
    return (prob_0, prob_1, prob_2)


def calculate_vot_for_player(new_player, my_team_by_position, team_odds, odds_col):
    """
    Calculate Value Over My Team for a single player.
    
    VOT represents the marginal value of adding this player to my roster.
    
    Logic by position:
    - QB/TE: Compare to your starter (1st player at position)
    - RB/WR: Compare to your 2nd best at position OR your FLEX (after top 2 RBs and top 2 WRs), whichever is worse
    """
    pos = new_player['position']
    new_points = new_player['half_ppr_points']
    new_p = get_team_play_probability(new_player['team'], team_odds, odds_col)
    
    # No value if team won't play
    if new_p == 0:
        return 0.0
    
    # Get all my team players at this position, sorted by expected value
    my_position_players = my_team_by_position.get(pos, [])
    
    if pos == 'QB':
        # QB: Compare to ALL players better than new player
        
        # Find all players better than the new player (by projected points)
        better_players = [p for p in my_position_players if p['half_ppr_points'] > new_points]
        
        if not better_players:
            # New player is better than all my players at this position - full value
            return new_p * new_points
        
        # Calculate probability that ALL better players are eliminated
        prob_all_eliminated = 1.0
        for better_p in better_players:
            prob_all_eliminated *= (1 - better_p['play_prob'])
        # All better players eliminated - new player provides full value
        return prob_all_eliminated * new_p * new_points
    
    elif pos in ['RB', 'WR']:
        # RB/WR: Can start if:
        # - 0 or 1 better players available in their position, OR
        # - 2 better players available in their position AND (0, 1, or 2 better players 
        #   available in the other RB/WR position) AND (0 or 1 better TE available)
        
        # Find all players better than the new player (by projected points) at this position
        better_players_this_pos = [p for p in my_position_players if p['half_ppr_points'] > new_points]
        
        if not better_players_this_pos:
            # New player is better than all my players at this position - full value
            return new_p * new_points
        
        # Get availability probabilities for this position
        prob_0_this, prob_1_this, prob_2_this = calculate_availability_probs(better_players_this_pos)
        
        # Case 1: 0 or 1 better players available in this position - can start at position
        prob_start_at_position = prob_0_this + prob_1_this
        
        # Case 2: 2 better players available in this position - can only start if FLEX eligible
        # Need to check other positions
        other_pos = 'WR' if pos == 'RB' else 'RB'
        other_position_players = my_team_by_position.get(other_pos, [])
        
        # Find better players in the other RB/WR position
        better_players_other_pos = [p for p in other_position_players if p['half_ppr_points'] > new_points]
        prob_0_other, prob_1_other, prob_2_other = calculate_availability_probs(better_players_other_pos)
        
        # Find better TEs
        te_players = my_team_by_position.get('TE', [])
        better_tes = [p for p in te_players if p['half_ppr_points'] > new_points]
        prob_0_te, prob_1_te, prob_2_te = calculate_availability_probs(better_tes)
        
        # For FLEX: Need (0, 1, or 2 better in other RB/WR) AND (0 or 1 better TE)
        prob_flex_eligible = (prob_0_other + prob_1_other + prob_2_other) * (prob_0_te + prob_1_te)
        
        # Total probability of starting:
        # - Start at position: prob_0_this + prob_1_this
        # - Start as FLEX (when 2 better in position): prob_2_this * prob_flex_eligible
        prob_start = prob_start_at_position + (prob_2_this * prob_flex_eligible)
        
        return prob_start * new_p * new_points
    
    elif pos == 'TE':
        # TE: Can start if 0 better TEs available (non-FLEX start)
        # Otherwise can only be FLEX if eligible
        
        # Find all players better than the new player (by projected points)
        better_players = [p for p in my_position_players if p['half_ppr_points'] > new_points]
        
        if not better_players:
            # New player is better than all my TEs - full value
            return new_p * new_points
        
        # Get availability probabilities for TE
        prob_0_te, prob_1_te = calculate_availability_probs(better_players)
        
        # Case 1: 0 better TEs available - can start at TE position
        prob_start_at_te = prob_0_te
        
        # Case 2: 1+ better TEs available - can only start if FLEX eligible
        # Need to check RB and WR positions
        rb_players = my_team_by_position.get('RB', [])
        wr_players = my_team_by_position.get('WR', [])
        
        # Find better RBs and WRs
        better_rbs = [p for p in rb_players if p['half_ppr_points'] > new_points]
        better_wrs = [p for p in wr_players if p['half_ppr_points'] > new_points]
        
        prob_0_rb, prob_1_rb, prob_2_rb = calculate_availability_probs(better_rbs)
        prob_0_wr, prob_1_wr, prob_2_wr = calculate_availability_probs(better_wrs)
        
        # For FLEX: Need (0, 1, or 2 better RBs) AND (0, 1, or 2 better WRs)
        prob_flex_eligible = (prob_0_rb + prob_1_rb + prob_2_rb) * (prob_0_wr + prob_1_wr + prob_2_wr)
        
        # Total probability of starting:
        # - Start at TE: prob_0_te
        # - Start as FLEX (when 1+ better TEs): (prob_1_te + prob_2_te) * prob_flex_eligible
        prob_start = prob_start_at_te + (prob_1_te * prob_flex_eligible)
        
        return prob_start * new_p * new_points
    
    else:
        # Unknown position - no value
        raise ValueError(f"Unknown position: {pos}")


def calculate_weekly_vot(players, my_team_names, team_odds, odds_col, round_name):
    """Calculate VOT for all players for a single week"""
    
    # Get all my team players grouped by position
    my_team_by_position = get_my_team_players_by_position(my_team_names, players, team_odds, odds_col)
    
    # Print my team players by position for this week
    print(f"\n{'='*60}")
    print(f"MY TEAM - {round_name.upper()}")
    print(f"{'='*60}")
    
    for pos in ['QB', 'RB', 'WR', 'TE']:
        pos_players = my_team_by_position.get(pos, [])
        if pos_players:
            print(f"\n  {pos}:")
            for p in pos_players:
                print(f"    {p['name']:<25} ({p['team']}) - "
                      f"{p['half_ppr_points']:.2f} pts, {p['play_prob']:.1%} play prob, "
                      f"{p['expected_points']:.2f} EV")
        else:
            print(f"\n  {pos}: (empty)")
    
    # Calculate VOT for each player
    for player in players:
        vot = calculate_vot_for_player(player, my_team_by_position, team_odds, odds_col)
        player['vot'] = vot
        player['play_prob'] = get_team_play_probability(player['team'], team_odds, odds_col)
    
    return players


def main():
    print("=" * 70)
    print("VALUE OVER TEAM (VOT) CALCULATOR")
    print("=" * 70)
    
    # Load my team
    my_team_names = load_my_team('my_team.txt')
    
    if not my_team_names:
        print("\nNo players in my_team.txt. Please add your drafted players.")
        print("VOT calculations require knowing your team composition.")
        return None
    
    print(f"\nMy Team ({len(my_team_names)} players):")
    for name in my_team_names:
        print(f"  - {name}")
    
    # Load team odds
    print("\nLoading team advancement odds...")
    team_odds = load_team_odds('teamodds.csv')
    
    # Check if projection files exist, generate if needed
    required_files = [week_info['filename'] for week_info in PLAYOFF_WEEKS.values()]
    if not ensure_projections_exist(required_files):
        print("Warning: Some projection files are missing. Continuing with available files...")
    
    all_weekly_vot = {}
    total_vot = defaultdict(lambda: {'total_vot': 0, 'total_points': 0})
    
    # Process each playoff week
    for round_name, week_info in PLAYOFF_WEEKS.items():
        filename = week_info['filename']
        odds_col = week_info['odds_col']
        
        # Load projections
        players = load_projections(filename)
        
        if not players:
            print(f"\nSkipping {round_name} - no projections found")
            continue
        
        # Validate my team names
        all_player_names = {p['name'] for p in players}
        missing = [n for n in my_team_names if n not in all_player_names]
        if missing:
            print(f"\nWarning: Players not found in {filename}:")
            for name in missing:
                print(f"  - {name}")
        
        # Calculate VOT for this week
        players = calculate_weekly_vot(players, my_team_names, team_odds, odds_col, round_name)
        
        all_weekly_vot[round_name] = players
        
        # Accumulate total VOT
        for p in players:
            key = p['name']
            total_vot[key]['name'] = p['name']
            total_vot[key]['position'] = p['position']
            total_vot[key]['team'] = p['team']
            total_vot[key]['total_vot'] += p['vot']
            total_vot[key]['total_points'] += p['half_ppr_points'] * p['play_prob']
        
        # Export weekly VOT
        output_file = get_output_path(filename.replace('.csv', '_vot.csv'))
        players.sort(key=lambda x: x['vot'], reverse=True)
        
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'name', 'position', 'team', 'half_ppr_points', 'play_prob', 'vot'
            ])
            writer.writeheader()
            for p in players:
                writer.writerow({
                    'name': p['name'],
                    'position': p['position'],
                    'team': p['team'],
                    'half_ppr_points': round(p['half_ppr_points'], 2),
                    'play_prob': round(p['play_prob'], 3),
                    'vot': round(p['vot'], 2),
                })
        
        print(f"\n  Exported VOT to: {output_file}")
        
        # Show top VOT players for this week
        print(f"\n  Top 10 by VOT ({round_name}):")
        for i, p in enumerate(players[:10], 1):
            on_team = " (MY TEAM)" if p['name'] in my_team_names else ""
            print(f"    {i:>2}. {p['name']:<25} ({p['position']}) - "
                  f"VOT: {p['vot']:>6.2f}, Pts: {p['half_ppr_points']:>6.2f}{on_team}")
    
    # Export total VOT across all weeks
    total_list = list(total_vot.values())
    total_list.sort(key=lambda x: x['total_vot'], reverse=True)
    
    total_vot_file = get_output_path('total_vot.csv')
    with open(total_vot_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'name', 'position', 'team', 'total_vot', 'total_points'
        ])
        writer.writeheader()
        for p in total_list:
            writer.writerow({
                'name': p['name'],
                'position': p['position'],
                'team': p['team'],
                'total_vot': round(p['total_vot'], 2),
                'total_points': round(p['total_points'], 2),
            })
    
    print("\n" + "=" * 70)
    print("TOTAL VOT ACROSS ALL WEEKS")
    print("=" * 70)
    print(f"\n{'Rank':<5} {'Player':<25} {'Pos':<4} {'Team':<5} {'Total VOT':<12} {'Total Pts':<12}")
    print("-" * 70)
    
    for i, p in enumerate(total_list[:30], 1):
        on_team = "*" if p['name'] in my_team_names else ""
        print(f"{i:<5} {p['name']:<25} {p['position']:<4} {p['team']:<5} "
              f"{p['total_vot']:<12.2f} {p['total_points']:<12.2f} {on_team}")
    
    print("\n* = On my team")
    print(f"\nExported total VOT to: {total_vot_file}")
    
    return total_list


if __name__ == '__main__':
    main()


