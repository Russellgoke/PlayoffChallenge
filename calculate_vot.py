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
    
    if pos == 'QB' or pos == 'TE':
        # QB and TE: Compare to ALL players better than new player
        # If ANY better player plays, new player's VOT is zero
        
        if not my_position_players:
            # No player at this position - full value
            return new_p * new_points
        
        # Find all players better than the new player (by projected points)
        better_players = [p for p in my_position_players if p['half_ppr_points'] > new_points]
        
        if not better_players:
            # New player is better than all my players at this position - full value
            return new_p * new_points
        
        # Calculate probability that ANY better player will play
        # P(any play) = 1 - P(all eliminated)
        # P(all eliminated) = product of (1 - play_prob) for each better player
        prob_all_eliminated = 1.0
        for better_p in better_players:
            prob_all_eliminated *= (1 - better_p['play_prob'])
        
        prob_any_play = 1 - prob_all_eliminated
        
        # If any better player plays, new player has zero value
        if prob_any_play > 0:
            return 0.0
        
        # All better players eliminated - new player provides full value
        return new_p * new_points
    
    elif pos in ['RB', 'WR']:
        # RB/WR: Compare to all better players at position
        # New player has value only if fewer than 2 better players are available
        
        # Find all players better than the new player (by projected points)
        better_players = [p for p in my_position_players if p['half_ppr_points'] > new_points]
        
        if not better_players:
            # New player is better than all my players at this position - full value
            return new_p * new_points
        
        # Calculate probability that fewer than 2 better players are available
        # This means the new player can be RB2/WR2 or better
        
        # Calculate probability that 2+ better players are available
        # P(2+ available) = 1 - P(0 available) - P(1 available)
        
        # P(0 available) = product of (1 - play_prob) for all better players
        prob_0_available = 1.0
        for better_p in better_players:
            prob_0_available *= (1 - better_p['play_prob'])
        
        # P(1 available) = sum over each better player of:
        #   (that player's play_prob) * (all others eliminated)
        prob_1_available = 0.0
        for i, better_p in enumerate(better_players):
            prob_this_plays = better_p['play_prob']
            prob_others_eliminated = 1.0
            for j, other_p in enumerate(better_players):
                if i != j:
                    prob_others_eliminated *= (1 - other_p['play_prob'])
            prob_1_available += prob_this_plays * prob_others_eliminated
                
        # Position value: only if fewer than 2 better players available
        # If 2+ better players are available, new player can't be RB1/RB2 or WR1/WR2
        position_vot = (prob_0_available + prob_1_available) * new_p * new_points
        
        # FLEX value: New player must be better than BOTH 3rd best RB AND 3rd best WR
        # (and better than best TE if TE is being used as FLEX)
        top_2_rbs = my_team_by_position.get('RB', [])[:2]
        top_2_wrs = my_team_by_position.get('WR', [])[:2]
        guaranteed_starters = set()
        for p in top_2_rbs + top_2_wrs:
            guaranteed_starters.add(p['name'])
        
        # Get 3rd best RB and 3rd best WR
        rb_3rd = my_team_by_position.get('RB', [])[2] if len(my_team_by_position.get('RB', [])) >= 3 else None
        wr_3rd = my_team_by_position.get('WR', [])[2] if len(my_team_by_position.get('WR', [])) >= 3 else None
        
        # Get best TE (if not already starting)
        best_te = None
        te_players = my_team_by_position.get('TE', [])
        if te_players:
            best_te = te_players[0]  # Already sorted by projected points
        
        flex_vot = 0.0
        
        # Check if new player is better than 3rd RB (if exists)
        better_than_rb3 = True
        if rb_3rd:
            better_than_rb3 = new_points > rb_3rd['half_ppr_points']
        
        # Check if new player is better than 3rd WR (if exists)
        better_than_wr3 = True
        if wr_3rd:
            better_than_wr3 = new_points > wr_3rd['half_ppr_points']
        
        # Check if new player is better than best TE (if TE is FLEX candidate)
        better_than_te = True
        if best_te and best_te['name'] not in guaranteed_starters:
            better_than_te = new_points > best_te['half_ppr_points']
        
        # New player is FLEX-eligible if better than both 3rd RB and 3rd WR
        # (and better than TE if TE is in the mix)
        if better_than_rb3 and better_than_wr3:
            # Determine the best FLEX candidate (worst of the ones new player beats)
            flex_candidates = []
            if rb_3rd:
                flex_candidates.append(rb_3rd)
            if wr_3rd:
                flex_candidates.append(wr_3rd)
            if best_te and best_te['name'] not in guaranteed_starters:
                flex_candidates.append(best_te)
            
            if flex_candidates:
                # Find worst FLEX candidate (lowest projected points)
                worst_flex = min(flex_candidates, key=lambda x: x['half_ppr_points'])
                
                # Calculate probability that worst FLEX is eliminated
                # Actually, we need probability that ALL FLEX candidates are eliminated
                # because new player needs to beat all of them
                prob_all_flex_eliminated = 1.0
                for flex_candidate in flex_candidates:
                    prob_all_flex_eliminated *= (1 - flex_candidate['play_prob'])
                
                flex_vot = prob_all_flex_eliminated * new_p * new_points
        
        # Return maximum of position value and FLEX value
        return max(position_vot, flex_vot)
    
    else:
        # Unknown position - no value
        return 0.0


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
        output_file = filename.replace('.csv', '_vot.csv')
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
    
    with open('total_vot.csv', 'w', newline='', encoding='utf-8') as f:
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
    print(f"\nExported total VOT to: total_vot.csv")
    
    return total_list


if __name__ == '__main__':
    main()


