"""
Utility functions for playoff challenge calculations.
Shared functions used across multiple calculation scripts.
"""

import csv


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
        verbose: If True, print loaded odds
    
    Returns:
        Dict mapping team names to odds dict with keys:
        - 'DIV APP': Divisional Appearance probability
        - 'Conf App': Conference Appearance probability
        - 'Conf Win': Conference Win probability
    """
    team_odds = {}
    
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                team = row['Team'].strip()
                team_odds[team] = {
                    'DIV APP': parse_pct(row.get('Divisional Appearance', '0%')),
                    'Conf App': parse_pct(row.get('Conference Appearance', '0%')),
                    'Conf Win': parse_pct(row.get('Conference Win', '0%')),
                }
        
        if verbose:
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
    """
    Load player projections from CSV file.
    
    Args:
        filename: Path to projections CSV file
    
    Returns:
        List of player dicts with keys: name, position, team, half_ppr_points
    """
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


def load_my_team(filename='my_team.txt'):
    """
    Load my team players from text file.
    
    Args:
        filename: Path to team file (one player name per line, # for comments)
    
    Returns:
        List of player names
    """
    my_team = []
    
    try:
        with open(filename, 'r', encoding='utf-8-sig') as f:
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
        odds_col: Column name for odds ('DIV APP', 'Conf App', 'Conf Win') or None for Wild Card
    
    Returns:
        Float probability (0.0 to 1.0)
    """
    if odds_col is None:
        # Wild Card - teams with 100% DIV APP have a bye (don't play Wild Card)
        div_app = team_odds.get(team, {}).get('DIV APP', 0.0)
        if div_app >= 1.0:
            # Team has a bye - they don't play Wild Card
            return 0.0
        # Team plays Wild Card at 100% (they're in the playoffs)
        return 1.0
    return team_odds.get(team, {}).get(odds_col, 0.0)


def load_total_values(filename='total_playoff_value.csv'):
    """
    Load total playoff values from CSV.
    
    Args:
        filename: Path to total playoff value CSV file
    
    Returns:
        List of player dicts with keys: name, position, team, total_vor, total_points
    """
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
    """
    Load list of drafted players from text file.
    
    Args:
        filename: Path to drafted players file (comma or newline separated)
    
    Returns:
        List of player names
    """
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


def load_vor_file(filename):
    """
    Load VOR data from CSV file.
    
    Args:
        filename: Path to VOR CSV file
    
    Returns:
        Dict mapping player names to player data with keys:
        position, team, half_ppr_points, vor
    """
    players = {}
    
    try:
        with open(filename, 'r', encoding='utf-8') as f:
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

