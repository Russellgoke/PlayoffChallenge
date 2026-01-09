import csv
import sys
import os
import random
import hashlib
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
    calculate_all_baselines,
)

# Playoff weeks and their corresponding odds columns
PLAYOFF_WEEKS = {
    'Wild Card': {'filename': 'playoff_projections_wildcard.csv', 'odds_col': 'Wild Card Appearance'},
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




_BASELINE_SIM_CACHE = {}


def _stable_int_seed(s: str) -> int:
    """Deterministic 32-bit-ish seed from a string (stable across runs)."""
    h = hashlib.md5(s.encode('utf-8')).digest()
    return int.from_bytes(h[:8], byteorder='little', signed=False) % (2**32)


def _flatten_my_roster(my_team_by_position):
    """Flatten my roster dict into a stable list of players with play_prob present."""
    roster = []
    for pos, players in (my_team_by_position or {}).items():
        for p in players:
            # Only include standard fantasy positions we can actually start
            if p.get('position') in ('QB', 'RB', 'WR', 'TE'):
                roster.append(p)
    # Stable ordering for caching
    roster.sort(key=lambda x: (x.get('position', ''), x.get('name', '')))
    return roster


def _roster_fingerprint(roster_players):
    """Hashable fingerprint for caching baseline simulations."""
    fp = []
    for p in roster_players:
        fp.append((
            p.get('name', ''),
            p.get('position', ''),
            p.get('team', ''),
            round(float(p.get('half_ppr_points', 0.0)), 4),
            round(float(p.get('play_prob', 0.0)), 6),
        ))
    return tuple(fp)


def _optimal_lineup_points(mask, positions, points, baselines, extra_pos=None, extra_points=0.0):
    """
    Given an availability bitmask for the roster, compute optimal lineup points using
    raw projected points for selection (only players who "play" are eligible).
    
    Empty slots are filled with baseline replacement values.
    
    Args:
        mask: Bitmask of which roster players are available
        positions: List of positions for each roster player
        points: List of projected points for each roster player
        baselines: Dict of baseline values by position slot (QB, RB1, RB2, WR1, WR2, TE, FLEX)
        extra_pos: Position of extra player to consider (optional)
        extra_points: Points of extra player (optional)
    """
    qbs, rbs, wrs, tes = [], [], [], []

    for i, pos in enumerate(positions):
        if (mask >> i) & 1:
            pts = points[i]
            if pos == 'QB':
                qbs.append(pts)
            elif pos == 'RB':
                rbs.append(pts)
            elif pos == 'WR':
                wrs.append(pts)
            elif pos == 'TE':
                tes.append(pts)

    if extra_pos in ('QB', 'RB', 'WR', 'TE') and extra_points > 0:
        if extra_pos == 'QB':
            qbs.append(extra_points)
        elif extra_pos == 'RB':
            rbs.append(extra_points)
        elif extra_pos == 'WR':
            wrs.append(extra_points)
        elif extra_pos == 'TE':
            tes.append(extra_points)

    qbs.sort(reverse=True)
    rbs.sort(reverse=True)
    wrs.sort(reverse=True)
    tes.sort(reverse=True)

    # Fill positions, using baselines for empty slots
    qb = qbs[0] if qbs else baselines.get('QB', 0.0)
    
    # RB slots (need 2)
    rb1 = rbs[0] if len(rbs) >= 1 else baselines.get('RB1', 0.0)
    rb2 = rbs[1] if len(rbs) >= 2 else baselines.get('RB2', 0.0)
    
    # WR slots (need 2)
    wr1 = wrs[0] if len(wrs) >= 1 else baselines.get('WR1', 0.0)
    wr2 = wrs[1] if len(wrs) >= 2 else baselines.get('WR2', 0.0)
    
    # TE slot
    te = tes[0] if tes else baselines.get('TE', 0.0)

    # FLEX: best remaining player, or baseline if none
    flex_candidates = rbs[2:] + wrs[2:] + tes[1:]
    flex = max(flex_candidates) if flex_candidates else baselines.get('FLEX', 0.0)

    return qb + rb1 + rb2 + wr1 + wr2 + te + flex


def _get_or_build_baseline_sim(my_team_by_position, team_odds, odds_col, baselines):
    """
    Build (and cache) baseline Monte Carlo simulation for the current roster + round.

    Args:
        my_team_by_position: Dict of position -> list of player dicts
        team_odds: Dict of team advancement odds
        odds_col: Column name for odds
        baselines: Dict of baseline values by position slot (from calculate_all_baselines)

    Returns dict with:
      - names_set
      - positions, points, probs
      - masks (len n_sims)
      - baseline_scores (len n_sims)
      - baseline_expected
      - n_sims
      - baselines
    """
    roster_players = _flatten_my_roster(my_team_by_position)

    n_sims = int(os.environ.get('VOT_SIMULATIONS', '4000'))
    n_sims = max(500, min(n_sims, 50000))

    # Include baselines in cache key since they affect scores
    baselines_tuple = tuple(sorted(baselines.items()))
    fp = _roster_fingerprint(roster_players)
    cache_key = (odds_col, fp, n_sims, baselines_tuple)
    cached = _BASELINE_SIM_CACHE.get(cache_key)
    if cached is not None:
        return cached

    names_set = {p.get('name', '') for p in roster_players}
    positions = [p.get('position') for p in roster_players]
    points = [float(p.get('half_ppr_points', 0.0)) for p in roster_players]

    # Use play_prob already computed on my roster entries (via get_my_team_players_by_position)
    probs = [float(p.get('play_prob', 0.0)) for p in roster_players]

    seed = _stable_int_seed(f"{odds_col}|{fp}|{n_sims}")
    rng = random.Random(seed)

    masks = []
    baseline_scores = []

    for _ in range(n_sims):
        mask = 0
        for i, prob in enumerate(probs):
            if rng.random() < prob:
                mask |= (1 << i)
        masks.append(mask)
        baseline_scores.append(_optimal_lineup_points(mask, positions, points, baselines))

    baseline_expected = sum(baseline_scores) / float(n_sims) if n_sims else 0.0

    sim = {
        'names_set': names_set,
        'positions': positions,
        'points': points,
        'probs': probs,
        'masks': masks,
        'baseline_scores': baseline_scores,
        'baseline_expected': baseline_expected,
        'n_sims': n_sims,
        'odds_col': odds_col,
        'baselines': baselines,
    }
    _BASELINE_SIM_CACHE[cache_key] = sim
    return sim


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


def calculate_vot_for_player(new_player, my_team_by_position, team_odds, odds_col, baselines):
    """
    Calculate Value Over My Team for a single player.
    
    New definition (marginal lineup value):
      VOT = E[optimal roster points WITH this player] - E[optimal roster points WITHOUT this player]

    Where "optimal roster points" for a round is computed by:
      - sampling which of your roster players actually play in that round
      - choosing starters by RAW projected points among those who play (QB, RBx2, WRx2, TE, FLEX)
      - empty slots are filled with baseline replacement values
      - scoring is raw points (since availability is already sampled)
    
    Args:
        new_player: Player dict to evaluate
        my_team_by_position: Dict of position -> list of player dicts
        team_odds: Dict of team advancement odds
        odds_col: Column name for odds
        baselines: Dict of baseline values by position slot (from calculate_all_baselines)
    """
    pos = new_player.get('position')
    if pos not in ('QB', 'RB', 'WR', 'TE'):
        return 0.0

    # If player is already on my roster, adding them provides no marginal value
    baseline_sim = _get_or_build_baseline_sim(my_team_by_position, team_odds, odds_col, baselines)
    if new_player.get('name', '') in baseline_sim['names_set']:
        return 0.0

    new_points = float(new_player.get('half_ppr_points', 0.0))
    if new_points <= 0:
        return 0.0

    new_p = get_team_play_probability(new_player.get('team', ''), team_odds, odds_col)
    if new_p <= 0:
        return 0.0

    # Use a deterministic RNG per (player, round) so results are stable across runs
    seed = _stable_int_seed(f"{odds_col}|{new_player.get('name','')}|{new_player.get('team','')}|{new_points:.4f}|{baseline_sim['n_sims']}")
    rng = random.Random(seed)

    positions = baseline_sim['positions']
    points = baseline_sim['points']
    masks = baseline_sim['masks']
    baseline_scores = baseline_sim['baseline_scores']
    n_sims = baseline_sim['n_sims']

    delta_sum = 0.0
    for i in range(n_sims):
        if rng.random() < new_p:
            with_score = _optimal_lineup_points(masks[i], positions, points, baselines, extra_pos=pos, extra_points=new_points)
            delta_sum += (with_score - baseline_scores[i])
        # else: delta += 0 (same lineup as baseline)

    return delta_sum / float(n_sims) if n_sims else 0.0


def calculate_weekly_vot(players, my_team_names, team_odds, odds_col, round_name):
    """Calculate VOT for all players for a single week"""
    
    # Calculate baselines first (using raw projected points from all players)
    baselines = calculate_all_baselines(players, team_odds, odds_col, round_name, verbose=True)
    
    # Get all my team players grouped by position
    my_team_by_position = get_my_team_players_by_position(my_team_names, players, team_odds, odds_col)
    
    # Print my team players by position for this week
    print(f"\n  MY TEAM:")
    
    for pos in ['QB', 'RB', 'WR', 'TE']:
        pos_players = my_team_by_position.get(pos, [])
        if pos_players:
            print(f"    {pos}:")
            for p in pos_players:
                print(f"      {p['name']:<25} ({p['team']}) - "
                      f"{p['half_ppr_points']:.2f} pts, {p['play_prob']:.1%} play prob")
        else:
            print(f"    {pos}: (empty - will use baseline {baselines.get(pos, baselines.get(pos + '1', 0)):.2f} pts)")
    
    # Calculate VOT for each player
    for player in players:
        vot = calculate_vot_for_player(player, my_team_by_position, team_odds, odds_col, baselines)
        player['vot'] = vot
        player['play_prob'] = get_team_play_probability(player['team'], team_odds, odds_col)
    
    return players, baselines


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
        players, baselines = calculate_weekly_vot(players, my_team_names, team_odds, odds_col, round_name)
        
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


