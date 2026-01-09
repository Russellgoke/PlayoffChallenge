"""
Utility functions for playoff challenge calculations.
Shared functions used across multiple calculation scripts.
"""

import csv
import os

# Output directory for generated CSV files
OUTPUT_DIR = 'output'
# Input directory for input text files
INPUT_DIR = 'input'


def get_output_path(filename):
    """
    Get the output path for a CSV file.
    Creates the output directory if it doesn't exist.
    
    Args:
        filename: Name of the output file (e.g., 'draft_value.csv')
    
    Returns:
        Path to the file in the output directory
    """
    # Create output directory if it doesn't exist
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
    
    return os.path.join(OUTPUT_DIR, filename)


def get_input_path(filename):
    """
    Get the input path for a text file.
    Creates the input directory if it doesn't exist.
    
    Args:
        filename: Name of the input file (e.g., 'my_team.txt')
    
    Returns:
        Path to the file in the input directory (or root if not found in input)
    """
    # Create input directory if it doesn't exist
    if not os.path.exists(INPUT_DIR):
        os.makedirs(INPUT_DIR)
    
    # Try input directory first, then root
    filepath = os.path.join(INPUT_DIR, filename)
    if not os.path.exists(filepath):
        filepath = filename
    
    return filepath


def parse_pct(s):
    """Parse percentage string to float (0.0 to 1.0)"""
    if not s:
        return 0.0
    s = str(s).strip().replace('%', '').replace(',', '')
    try:
        return float(s) / 100
    except:
        return 0.0


def load_team_odds(filename='teamodds.csv', verbose=False):
    """
    Load team advancement odds from CSV file.
    
    Args:
        filename: Path to team odds CSV file
                  Checks input/ folder first, then root
        verbose: If True, print loaded odds
    
    Returns:
        Dict mapping team names to odds dict with keys:
        - 'Wild Card Appearance': Wild Card Appearance probability
        - 'DIV APP': Divisional Appearance probability
        - 'Conf App': Conference Appearance probability
        - 'Conf Win': Conference Win probability
    """
    team_odds = {}
    
    # Try input directory first, then root
    filepath = get_input_path(filename)
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Normalize row keys by stripping whitespace for easier access
                normalized_row = {k.strip(): v for k, v in row.items()}
                
                team = normalized_row.get('Team', '').strip()
                if not team:
                    continue
                    
                team_odds[team] = {
                    'Wild Card Appearance': parse_pct(normalized_row.get('Wild Card Appearance', '0%')),
                    'DIV APP': parse_pct(normalized_row.get('Divisional Appearance', '0%')),
                    'Conf App': parse_pct(normalized_row.get('Conference Appearance', '0%')),
                    'Conf Win': parse_pct(normalized_row.get('Conference Win', '0%')),
                }
        
        if verbose:
            print(f"Loaded odds for {len(team_odds)} teams:")
            for team, odds in team_odds.items():
                print(f"  {team}: WC={odds.get('Wild Card Appearance', 0):.1%}, DIV={odds['DIV APP']:.1%}, CONF={odds['Conf App']:.1%}, SB={odds['Conf Win']:.1%}")
        
        return team_odds
        
    except FileNotFoundError:
        print(f"Warning: {filename} not found.")
        return {}
    except Exception as e:
        print(f"Error loading team odds: {e}")
        return {}


def ensure_projections_exist(required_files):
    """
    Check if projection files exist, and run grabdata.py if they don't.
    
    Args:
        required_files: List of projection filenames to check
    
    Returns:
        True if all files exist (or were generated), False otherwise
    """
    missing_files = []
    
    for filename in required_files:
        # Check output folder first, then root
        filepath = get_output_path(filename)
        if not os.path.exists(filepath):
            filepath = filename
            if not os.path.exists(filepath):
                missing_files.append(filename)
    
    if missing_files:
        print(f"\nMissing projection files: {', '.join(missing_files)}")
        print("Running grabdata.py to generate projections...")
        try:
            # Import and run grabdata
            import grabdata
            grabdata.main()
            
            # Verify files were created
            still_missing = []
            for filename in missing_files:
                filepath = get_output_path(filename)
                if not os.path.exists(filepath):
                    filepath = filename
                    if not os.path.exists(filepath):
                        still_missing.append(filename)
            
            if still_missing:
                print(f"Warning: Some files still missing after running grabdata: {', '.join(still_missing)}")
                return False
            
            print("Projections generated successfully!")
            return True
        except Exception as e:
            print(f"Error running grabdata.py: {e}")
            return False
    
    return True


def ensure_vor_files_exist(required_files):
    """
    Check if VOR files exist, and run calculate_vor.py if they don't.
    
    Args:
        required_files: List of VOR filenames to check
    
    Returns:
        True if all files exist (or were generated), False otherwise
    """
    missing_files = []
    
    for filename in required_files:
        # Check output folder first, then root
        filepath = get_output_path(filename)
        if not os.path.exists(filepath):
            filepath = filename
            if not os.path.exists(filepath):
                missing_files.append(filename)
    
    if missing_files:
        print(f"\nMissing VOR files: {', '.join(missing_files)}")
        print("Running calculate_vor.py to generate VOR files...")
        try:
            # Import and run calculate_vor
            import calculate_vor
            calculate_vor.main()
            
            # Verify files were created
            still_missing = []
            for filename in missing_files:
                filepath = get_output_path(filename)
                if not os.path.exists(filepath):
                    filepath = filename
                    if not os.path.exists(filepath):
                        still_missing.append(filename)
            
            if still_missing:
                print(f"Warning: Some files still missing after running calculate_vor: {', '.join(still_missing)}")
                return False
            
            print("VOR files generated successfully!")
            return True
        except Exception as e:
            print(f"Error running calculate_vor.py: {e}")
            return False
    
    return True


def load_projections(filename):
    """
    Load player projections from CSV file.
    
    Args:
        filename: Path to projections CSV file
                  Checks output/ folder first, then root
    
    Returns:
        List of player dicts with keys: name, position, team, half_ppr_points
    """
    players = []
    
    # Try output directory first, then root
    filepath = get_output_path(filename)
    if not os.path.exists(filepath):
        filepath = filename
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
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


def load_my_team(filename='my_team.txt'):
    """
    Load my team players from text file.
    
    Args:
        filename: Path to team file (one player name per line, # for comments)
                  Checks input/ folder first, then root
    
    Returns:
        List of player names
    """
    my_team = []
    
    # Try input directory first, then root
    filepath = get_input_path(filename)
    
    try:
        with open(filepath, 'r', encoding='utf-8-sig') as f:
            for line in f:
                line = line.strip()
                # Skip empty lines and comments
                if line and not line.startswith('#'):
                    my_team.append(line)
        return my_team
    except FileNotFoundError:
        print(f"Note: {filename} not found. No team loaded.")
        return []
    except Exception as e:
        print(f"Error loading {filename}: {e}")
        return []


def get_team_play_probability(team, team_odds, odds_col):
    """
    Get probability that a team plays in this round.
    
    Args:
        team: Team abbreviation (e.g., 'SEA', 'LAR')
        team_odds: Dict of team odds (from load_team_odds)
        odds_col: Column name for odds ('Wild Card Appearance', 'DIV APP', 'Conf App', 'Conf Win')
                  or None for backwards compatibility (will use special Wild Card logic)
    
    Returns:
        Float probability (0.0 to 1.0)
    """
    if odds_col is None:
        # Backwards compatibility: Wild Card - teams with 100% DIV APP have a bye (don't play Wild Card)
        div_app = team_odds.get(team, {}).get('DIV APP', 0.0)
        if div_app >= 1.0:
            # Team has a bye - they don't play Wild Card
            return 0.0
        # Team plays Wild Card at 100% (they're in the playoffs)
        return 1.0
    return team_odds.get(team, {}).get(odds_col, 0.0)


def ensure_total_value_exists(filename='total_playoff_value.csv'):
    """
    Check if total_playoff_value.csv exists, and run calculate_total_value.py if it doesn't.
    
    Args:
        filename: Name of the total value CSV file
    
    Returns:
        True if file exists (or was generated), False otherwise
    """
    # Check output folder first, then root
    filepath = get_output_path(filename)
    if not os.path.exists(filepath):
        filepath = filename
        if not os.path.exists(filepath):
            print(f"\nMissing {filename}")
            print("Running calculate_total_value.py to generate total values...")
            try:
                # Import and run calculate_total_value
                import calculate_total_value
                calculate_total_value.main()
                
                # Verify file was created
                filepath = get_output_path(filename)
                if not os.path.exists(filepath):
                    filepath = filename
                    if not os.path.exists(filepath):
                        print(f"Warning: {filename} still missing after running calculate_total_value")
                        return False
                
                print("Total values generated successfully!")
                return True
            except Exception as e:
                print(f"Error running calculate_total_value.py: {e}")
                return False
    
    return True


def load_total_values(filename='total_playoff_value.csv'):
    """
    Load total playoff values from CSV.
    
    Args:
        filename: Path to total playoff value CSV file (checks output/ if not found in root)
    
    Returns:
        List of player dicts with keys: name, position, team, total_vot, total_points
    """
    players = []
    
    # Try output directory first, then root
    filepath = get_output_path(filename)
    if not os.path.exists(filepath):
        filepath = filename
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                players.append({
                    'name': row['name'],
                    'position': row['position'],
                    'team': row['team'],
                    'total_vot': float(row['total_vot']),
                    'total_points': float(row['total_points']),
                })
        return players
    except Exception as e:
        print(f"Error loading {filename}: {e}")
        return []


def load_drafted_players(filename='players_drafted.txt'):
    """
    Load list of drafted players from text file.
    
    Args:
        filename: Path to drafted players file (comma or newline separated)
                  Checks input/ folder first, then root
    
    Returns:
        List of player names
    """
    drafted = []
    
    # Try input directory first, then root
    filepath = get_input_path(filename)
    
    try:
        with open(filepath, 'r', encoding='utf-8-sig') as f:  # utf-8-sig handles BOM
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


def load_vor_file(filename):
    """
    Load VOR data from CSV file.
    
    Args:
        filename: Path to VOR CSV file (checks output/ if not found in root)
    
    Returns:
        Dict mapping player names to player data with keys:
        position, team, half_ppr_points, vor
    """
    players = {}
    
    # Try output directory first, then root
    filepath = get_output_path(filename)
    if not os.path.exists(filepath):
        filepath = filename
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = row['name']
                players[name] = {
                    'position': row['position'],
                    'team': row['team'],
                    'half_ppr_points': float(row['half_ppr_points']),
                    'vor': float(row['vor']),
                }
        return players
    except Exception as e:
        print(f"Error loading {filename}: {e}")
        return {}


def load_vot_file(filename):
    """
    Load VOT data from CSV file.
    
    Args:
        filename: Path to VOT CSV file (checks output/ if not found in root)
    
    Returns:
        Dict mapping player names to player data with keys:
        position, team, half_ppr_points, vot
    """
    players = {}
    
    # Try output directory first, then root
    filepath = get_output_path(filename)
    if not os.path.exists(filepath):
        filepath = filename
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = row['name']
                players[name] = {
                    'position': row['position'],
                    'team': row['team'],
                    'half_ppr_points': float(row['half_ppr_points']),
                    'vot': float(row['vot']),
                }
        return players
    except Exception as e:
        print(f"Error loading {filename}: {e}")
        return {}


# Replacement value target ranks for each position slot
REPLACEMENT_RANKS = {
    'QB': 7,
    'TE': 7,
    'WR1': 7,
    'WR2': 12,
    'RB1': 7,
    'RB2': 12,
    'FLEX': 27
}


def calculate_probability_weighted_baseline(players, position, target_rank, team_odds, odds_col):
    """
    Calculate the probability-weighted baseline for a position.
    
    Args:
        players: List of player dicts with 'half_ppr_points'
        position: Position to filter (e.g., 'QB', 'RB', 'WR', 'TE') or 'FLEX' for RB/WR/TE
        target_rank: The target rank for replacement (e.g., 3 for 3rd best available)
        team_odds: Dict of team advancement odds
        odds_col: Column name for odds (e.g., 'Wild Card Appearance', 'DIV APP', 'Conf App', 'Conf Win')
    
    Returns:
        Tuple of (baseline_value, baseline_player_name)
    """
    value_field = 'half_ppr_points'
    
    if position == 'FLEX':
        # FLEX is the best available among RB/WR/TE
        filtered = [p for p in players if p.get('position') in ['RB', 'WR', 'TE']]
    else:
        filtered = [p for p in players if p.get('position') == position]
    
    # Sort by value (descending)
    filtered.sort(key=lambda x: x.get(value_field, 0), reverse=True)
    
    if not filtered:
        return 0.0, "N/A"
    
    # Calculate cumulative probability
    cumulative_prob = 0.0
    baseline_value = 0.0
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


def calculate_all_baselines(players, team_odds, odds_col, round_name=None, verbose=True):
    """
    Calculate baselines for all position slots using raw projected points.
    
    Args:
        players: List of player dicts
        team_odds: Dict of team advancement odds
        odds_col: Column name for odds
        round_name: Name of round for display (optional)
        verbose: If True, print baselines
    
    Returns:
        Dict with keys: QB, TE, WR1, WR2, RB1, RB2, FLEX
    """
    baselines = {}
    
    if verbose and round_name:
        print(f"\n{'='*60}")
        print(f"REPLACEMENT BASELINES - {round_name.upper()}")
        print(f"{'='*60}")
    
    # QB
    val, name = calculate_probability_weighted_baseline(
        players, 'QB', REPLACEMENT_RANKS['QB'], team_odds, odds_col)
    baselines['QB'] = val
    if verbose:
        print(f"  QB  (rank {REPLACEMENT_RANKS['QB']}): {val:6.2f} pts - {name}")
    
    # TE
    val, name = calculate_probability_weighted_baseline(
        players, 'TE', REPLACEMENT_RANKS['TE'], team_odds, odds_col)
    baselines['TE'] = val
    if verbose:
        print(f"  TE  (rank {REPLACEMENT_RANKS['TE']}): {val:6.2f} pts - {name}")
    
    # WR1
    val, name = calculate_probability_weighted_baseline(
        players, 'WR', REPLACEMENT_RANKS['WR1'], team_odds, odds_col)
    baselines['WR1'] = val
    if verbose:
        print(f"  WR1 (rank {REPLACEMENT_RANKS['WR1']}): {val:6.2f} pts - {name}")
    
    # WR2
    val, name = calculate_probability_weighted_baseline(
        players, 'WR', REPLACEMENT_RANKS['WR2'], team_odds, odds_col)
    baselines['WR2'] = val
    if verbose:
        print(f"  WR2 (rank {REPLACEMENT_RANKS['WR2']}): {val:6.2f} pts - {name}")
    
    # RB1
    val, name = calculate_probability_weighted_baseline(
        players, 'RB', REPLACEMENT_RANKS['RB1'], team_odds, odds_col)
    baselines['RB1'] = val
    if verbose:
        print(f"  RB1 (rank {REPLACEMENT_RANKS['RB1']}): {val:6.2f} pts - {name}")
    
    # RB2
    val, name = calculate_probability_weighted_baseline(
        players, 'RB', REPLACEMENT_RANKS['RB2'], team_odds, odds_col)
    baselines['RB2'] = val
    if verbose:
        print(f"  RB2 (rank {REPLACEMENT_RANKS['RB2']}): {val:6.2f} pts - {name}")
    
    # FLEX
    val, name = calculate_probability_weighted_baseline(
        players, 'FLEX', REPLACEMENT_RANKS['FLEX'], team_odds, odds_col)
    baselines['FLEX'] = val
    if verbose:
        print(f"  FLEX (rank {REPLACEMENT_RANKS['FLEX']}): {val:6.2f} pts - {name}")
    
    return baselines

