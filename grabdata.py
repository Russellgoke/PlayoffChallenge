import os
import sys
from dotenv import load_dotenv
import requests
from collections import defaultdict
import csv

sys.stdout.reconfigure(encoding='utf-8')
load_dotenv()

api_key = os.getenv('THE_ODDS_API_KEY')
if not api_key:
    raise ValueError("API Key not found. Ensure it is set in your .env file.")

SPORT = 'americanfootball_nfl'
REGIONS = 'us'

# Half PPR Scoring Rules
SCORING = {
    'pass_yd': 0.04,      # 1 pt per 25 yards
    'pass_td': 4,
    'interception': -2,
    'rush_yd': 0.1,       # 1 pt per 10 yards
    'rush_td': 6,
    'rec_yd': 0.1,        # 1 pt per 10 yards
    'rec_td': 6,
    'reception': 0.5,     # Half PPR
}

# Playoff weeks configuration (Sleeper API week numbers)
# use_weekly=True: Use weekly projections, False: Use season average PPG
PLAYOFF_WEEKS = {
    19: {'name': 'Wild Card', 'filename': 'playoff_projections_wildcard.csv', 'use_weekly': True},
    20: {'name': 'Divisional', 'filename': 'playoff_projections_divisional.csv', 'use_weekly': False},
    21: {'name': 'Conference', 'filename': 'playoff_projections_conference.csv', 'use_weekly': False},
    22: {'name': 'Super Bowl', 'filename': 'playoff_projections_superbowl.csv', 'use_weekly': False},
}


def get_available_markets(event_id):
    url = f'https://api.the-odds-api.com/v4/sports/{SPORT}/events/{event_id}/odds'
    params = {'apiKey': api_key, 'regions': REGIONS}
    response = requests.get(url, params=params)
    if response.status_code == 200:
        data = response.json()
        markets = set()
        for book in data.get('bookmakers', []):
            for market in book.get('markets', []):
                markets.add(market['key'])
        return list(markets)
    return []


def get_playoff_events():
    url = f'https://api.the-odds-api.com/v4/sports/{SPORT}/events?apiKey={api_key}'
    response = requests.get(url)
    response.raise_for_status()
    events = response.json()
    print(f"Found {len(events)} NFL events")
    return events


def get_player_props(event_id, event_name, markets_list):
    url = f'https://api.the-odds-api.com/v4/sports/{SPORT}/events/{event_id}/odds'
    params = {
        'apiKey': api_key,
        'regions': REGIONS,
        'markets': ','.join(markets_list),
        'oddsFormat': 'american'
    }
    response = requests.get(url, params=params)
    if response.status_code != 200:
        print(f"  Warning: Could not get props for {event_name}: {response.status_code}")
        return None
    remaining = response.headers.get('x-requests-remaining', 'unknown')
    print(f"  API requests remaining: {remaining}")
    return response.json()


def extract_player_projections(props_data, event_name):
    players = defaultdict(lambda: {
        'pass_yds': 0, 'pass_tds': 0, 'interceptions': 0,
        'rush_yds': 0, 'rush_tds': 0, 'rec_yds': 0,
        'receptions': 0, 'anytime_td_prob': 0, 'game': event_name
    })
    if not props_data or 'bookmakers' not in props_data:
        return players
    market_values = defaultdict(lambda: defaultdict(list))
    for bookmaker in props_data.get('bookmakers', []):
        for market in bookmaker.get('markets', []):
            market_key = market['key']
            for outcome in market.get('outcomes', []):
                player_name = outcome.get('description', outcome.get('name', ''))
                point = outcome.get('point')
                if point is not None and outcome.get('name') == 'Over':
                    market_values[player_name][market_key].append(point)
    for player_name, markets in market_values.items():
        for market_key, values in markets.items():
            avg_value = sum(values) / len(values)
            if 'pass_yds' in market_key:
                players[player_name]['pass_yds'] = avg_value
            elif 'pass_tds' in market_key:
                players[player_name]['pass_tds'] = avg_value
            elif 'interceptions' in market_key:
                players[player_name]['interceptions'] = avg_value
            elif 'rush_yds' in market_key:
                players[player_name]['rush_yds'] = avg_value
            elif 'reception_yds' in market_key or 'receiving_yds' in market_key:
                players[player_name]['rec_yds'] = avg_value
            elif 'receptions' in market_key:
                players[player_name]['receptions'] = avg_value
    for bookmaker in props_data.get('bookmakers', []):
        for market in bookmaker.get('markets', []):
            if 'anytime_td' in market['key'] or 'td_scorer' in market['key']:
                for outcome in market.get('outcomes', []):
                    player_name = outcome.get('description', outcome.get('name', ''))
                    odds = outcome.get('price', 0)
                    if odds and odds > 0:
                        prob = 100 / (odds + 100)
                    elif odds and odds < 0:
                        prob = abs(odds) / (abs(odds) + 100)
                    else:
                        prob = 0
                    if prob > players[player_name]['anytime_td_prob']:
                        players[player_name]['anytime_td_prob'] = prob
    return players


def calculate_half_ppr_points(stats):
    points = 0
    points += stats['pass_yds'] * SCORING['pass_yd']
    points += stats['pass_tds'] * SCORING['pass_td']
    points += stats['interceptions'] * SCORING['interception']
    points += stats['rush_yds'] * SCORING['rush_yd']
    points += stats['rec_yds'] * SCORING['rec_yd']
    points += stats['receptions'] * SCORING['reception']
    if stats['pass_yds'] < 50:
        points += stats['anytime_td_prob'] * SCORING['rush_td']
    return round(points, 2)


def infer_position(stats):
    if stats['pass_yds'] >= 50:
        return 'QB'
    elif stats['receptions'] >= 1 or stats['rec_yds'] >= 10:
        if stats['rush_yds'] >= 20:
            return 'RB'
        return 'WR/TE'
    elif stats['rush_yds'] >= 10:
        return 'RB'
    return 'FLEX'


def export_to_csv(projections, filename='playoff_projections_half_ppr.csv'):
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'name', 'position', 'team', 'game', 'pass_yds', 'pass_tds',
            'rush_yds', 'rec_yds', 'receptions', 'td_prob', 'half_ppr_points', 'games_played'
        ], extrasaction='ignore')
        writer.writeheader()
        writer.writerows(projections)
    print(f"\n[OK] Projections exported to: {filename}")


def fetch_fantasypros_projections():
    """Fetch projections from FantasyPros API for playoff week"""
    print("\nFetching FantasyPros playoff projections...")
    
    # FantasyPros public projection endpoints
    base_url = "https://api.fantasypros.com/public/v2/json/nfl/2025/projections"
    
    all_players = []
    positions = ['QB', 'RB', 'WR', 'TE']
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json'
    }
    
    for pos in positions:
        try:
            # Try the FantasyPros public API
            url = f"{base_url}?position={pos}&week=18&scoring=HALF"
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                players = data.get('players', [])
                print(f"  {pos}: Found {len(players)} players")
                for p in players:
                    all_players.append({
                        'name': p.get('player_name', 'Unknown'),
                        'position': pos,
                        'team': p.get('team', ''),
                        'pass_yds': float(p.get('pass_yds', 0) or 0),
                        'pass_tds': float(p.get('pass_tds', 0) or 0),
                        'rush_yds': float(p.get('rush_yds', 0) or 0),
                        'rec_yds': float(p.get('rec_yds', 0) or 0),
                        'receptions': float(p.get('rec', 0) or 0),
                        'half_ppr_points': float(p.get('fpts', 0) or 0)
                    })
            else:
                print(f"  {pos}: API returned {response.status_code}")
        except Exception as e:
            print(f"  {pos}: Error - {e}")
    
    return all_players


def fetch_sleeper_projections(week=19, round_name='Wild Card', players_cache=None):
    """Fetch projections from Sleeper API for a specific week"""
    print(f"\nFetching Sleeper API projections for {round_name} (Week {week})...")
    
    # Get all NFL players from Sleeper (use cache if available)
    if players_cache is None:
        players_url = "https://api.sleeper.app/v1/players/nfl"
        try:
            response = requests.get(players_url, timeout=30)
            if response.status_code != 200:
                print(f"  Failed to fetch players: {response.status_code}")
                return [], None
            players_data = response.json()
            print(f"  Found {len(players_data)} total players in database")
        except Exception as e:
            print(f"  Error fetching players: {e}")
            return [], None
    else:
        players_data = players_cache
        print(f"  Using cached player database ({len(players_data)} players)")
    
    try:
        # Try playoff projections first, fall back to week 18 regular season
        urls_to_try = [
            f"https://api.sleeper.app/projections/nfl/2025/{week}?season_type=post&position[]=QB&position[]=RB&position[]=WR&position[]=TE",
            f"https://api.sleeper.app/projections/nfl/2025/18?season_type=regular&position[]=QB&position[]=RB&position[]=WR&position[]=TE",
        ]
        
        projections = {}
        used_fallback = False
        
        for i, projections_url in enumerate(urls_to_try):
            proj_response = requests.get(projections_url, timeout=30)
            if proj_response.status_code == 200:
                proj_data = proj_response.json()
                if isinstance(proj_data, list):
                    # Check if projections have actual values
                    has_values = False
                    for p in proj_data:
                        stats = p.get('stats', {})
                        if stats.get('pass_yd', 0) or stats.get('rush_yd', 0) or stats.get('rec_yd', 0):
                            has_values = True
                            break
                    
                    if has_values or i == len(urls_to_try) - 1:
                        for p in proj_data:
                            player_id = p.get('player_id')
                            if player_id:
                                projections[player_id] = p.get('stats', {})
                        if i > 0:
                            used_fallback = True
                            print(f"  (Using Week 18 projections as baseline - playoff data not yet available)")
                        break
        
        print(f"  Found {len(projections)} player projections for {round_name}")
        
        all_players = []
        positions_wanted = ['QB', 'RB', 'WR', 'TE']
        
        for player_id, player in players_data.items():
            if not isinstance(player, dict):
                continue
            pos = player.get('position', '')
            team = player.get('team', '')
            status = player.get('status', '')
            
            if pos not in positions_wanted:
                continue
            if not team:
                continue
            if status not in ['Active', 'Injured Reserve', None, '']:
                continue
            
            # Get projection stats
            proj = projections.get(player_id, {})
            
            # Skip players with no projections for this week
            if not proj:
                continue
            
            pass_yds = float(proj.get('pass_yd', 0) or 0)
            pass_tds = float(proj.get('pass_td', 0) or 0)
            rush_yds = float(proj.get('rush_yd', 0) or 0)
            rush_tds = float(proj.get('rush_td', 0) or 0)
            rec_yds = float(proj.get('rec_yd', 0) or 0)
            rec_tds = float(proj.get('rec_td', 0) or 0)
            receptions = float(proj.get('rec', 0) or 0)
            ints = float(proj.get('pass_int', 0) or 0)
            
            # Calculate half PPR points
            pts = 0
            pts += pass_yds * SCORING['pass_yd']
            pts += pass_tds * SCORING['pass_td']
            pts += ints * SCORING['interception']
            pts += rush_yds * SCORING['rush_yd']
            pts += rush_tds * SCORING['rush_td']
            pts += rec_yds * SCORING['rec_yd']
            pts += rec_tds * SCORING['rec_td']
            pts += receptions * SCORING['reception']
            
            name = player.get('full_name', f"{player.get('first_name', '')} {player.get('last_name', '')}")
            
            all_players.append({
                'name': name.strip(),
                'position': pos,
                'team': team,
                'game': f"{team} ({round_name})",
                'pass_yds': pass_yds,
                'pass_tds': pass_tds,
                'rush_yds': rush_yds,
                'rec_yds': rec_yds,
                'receptions': receptions,
                'td_prob': 0,
                'half_ppr_points': round(pts, 2)
            })
        
        # Sort by projected points
        all_players.sort(key=lambda x: x['half_ppr_points'], reverse=True)
        
        return all_players, players_data
        
    except Exception as e:
        print(f"  Error: {e}")
        return [], players_data


def fetch_season_averages(round_name='Playoffs', players_cache=None):
    """Fetch season stats and calculate half PPR average PPG"""
    print(f"\nFetching season averages for {round_name}...")
    
    # Get all NFL players from Sleeper (use cache if available)
    if players_cache is None:
        players_url = "https://api.sleeper.app/v1/players/nfl"
        try:
            response = requests.get(players_url, timeout=30)
            if response.status_code != 200:
                print(f"  Failed to fetch players: {response.status_code}")
                return [], None
            players_data = response.json()
            print(f"  Found {len(players_data)} total players in database")
        except Exception as e:
            print(f"  Error fetching players: {e}")
            return [], None
    else:
        players_data = players_cache
        print(f"  Using cached player database ({len(players_data)} players)")
    
    try:
        # Get season stats from Sleeper - try multiple endpoint formats
        stats_urls = [
            "https://api.sleeper.app/v1/stats/nfl/regular/2025",
            "https://api.sleeper.app/stats/nfl/regular/2025",
            "https://api.sleeper.app/v1/stats/nfl/2025/1",  # Fallback to week-by-week
        ]
        
        season_stats = {}
        
        for stats_url in stats_urls:
            stats_response = requests.get(stats_url, timeout=30)
            if stats_response.status_code == 200:
                stats_data = stats_response.json()
                if isinstance(stats_data, dict):
                    # Stats keyed by player_id
                    for player_id, stats in stats_data.items():
                        if isinstance(stats, dict):
                            season_stats[player_id] = stats
                    if season_stats:
                        print(f"  Stats loaded from: {stats_url}")
                        break
                elif isinstance(stats_data, list):
                    for p in stats_data:
                        player_id = p.get('player_id')
                        if player_id:
                            season_stats[player_id] = p.get('stats', {})
                    if season_stats:
                        print(f"  Stats loaded from: {stats_url}")
                        break
        
        # If no season stats available, calculate from weekly projections
        if not season_stats:
            print("  Season stats API not available, calculating from weekly data...")
            # Sum up projections from weeks 1-18
            for week in range(1, 19):
                week_url = f"https://api.sleeper.app/projections/nfl/2025/{week}?season_type=regular&position[]=QB&position[]=RB&position[]=WR&position[]=TE"
                week_response = requests.get(week_url, timeout=30)
                if week_response.status_code == 200:
                    week_data = week_response.json()
                    if isinstance(week_data, list):
                        for p in week_data:
                            player_id = p.get('player_id')
                            if player_id:
                                stats = p.get('stats', {})
                                if player_id not in season_stats:
                                    season_stats[player_id] = {'weeks': 0}
                                # Accumulate stats
                                for key, val in stats.items():
                                    if isinstance(val, (int, float)):
                                        current = season_stats[player_id].get(key, 0)
                                        season_stats[player_id][key] = current + val
                                season_stats[player_id]['weeks'] = season_stats[player_id].get('weeks', 0) + 1
            print(f"  Aggregated {len(season_stats)} players from weekly data")
        
        print(f"  Found {len(season_stats)} players with season stats")
        
        all_players = []
        positions_wanted = ['QB', 'RB', 'WR', 'TE']
        
        for player_id, player in players_data.items():
            if not isinstance(player, dict):
                continue
            pos = player.get('position', '')
            team = player.get('team', '')
            status = player.get('status', '')
            
            if pos not in positions_wanted:
                continue
            if not team:
                continue
            if status not in ['Active', 'Injured Reserve', None, '']:
                continue
            
            # Get season stats
            stats = season_stats.get(player_id, {})
            
            # Skip players with no stats
            if not stats:
                continue
            
            # Get games played (use gp, weeks from aggregation, or estimate)
            games_played = float(stats.get('gp', 0) or stats.get('weeks', 0) or 0)
            if games_played == 0:
                # Estimate games from stats presence
                if stats.get('pass_yd', 0) or stats.get('rush_yd', 0) or stats.get('rec_yd', 0):
                    games_played = 17  # Assume full season if stats exist but no GP
                else:
                    continue
            
            # Ensure reasonable games played value
            games_played = min(games_played, 18)
            
            # Get cumulative season stats
            pass_yds_total = float(stats.get('pass_yd', 0) or 0)
            pass_tds_total = float(stats.get('pass_td', 0) or 0)
            rush_yds_total = float(stats.get('rush_yd', 0) or 0)
            rush_tds_total = float(stats.get('rush_td', 0) or 0)
            rec_yds_total = float(stats.get('rec_yd', 0) or 0)
            rec_tds_total = float(stats.get('rec_td', 0) or 0)
            receptions_total = float(stats.get('rec', 0) or 0)
            ints_total = float(stats.get('pass_int', 0) or 0)
            
            # Calculate per-game averages
            pass_yds = pass_yds_total / games_played
            pass_tds = pass_tds_total / games_played
            rush_yds = rush_yds_total / games_played
            rush_tds = rush_tds_total / games_played
            rec_yds = rec_yds_total / games_played
            rec_tds = rec_tds_total / games_played
            receptions = receptions_total / games_played
            ints = ints_total / games_played
            
            # Calculate half PPR points per game
            pts = 0
            pts += pass_yds * SCORING['pass_yd']
            pts += pass_tds * SCORING['pass_td']
            pts += ints * SCORING['interception']
            pts += rush_yds * SCORING['rush_yd']
            pts += rush_tds * SCORING['rush_td']
            pts += rec_yds * SCORING['rec_yd']
            pts += rec_tds * SCORING['rec_td']
            pts += receptions * SCORING['reception']
            
            name = player.get('full_name', f"{player.get('first_name', '')} {player.get('last_name', '')}")
            
            all_players.append({
                'name': name.strip(),
                'position': pos,
                'team': team,
                'game': f"{team} ({round_name})",
                'pass_yds': round(pass_yds, 1),
                'pass_tds': round(pass_tds, 2),
                'rush_yds': round(rush_yds, 1),
                'rec_yds': round(rec_yds, 1),
                'receptions': round(receptions, 1),
                'td_prob': 0,
                'half_ppr_points': round(pts, 2),
                'games_played': int(games_played)
            })
        
        # Sort by projected points
        all_players.sort(key=lambda x: x['half_ppr_points'], reverse=True)
        
        print(f"  Calculated season averages for {len(all_players)} players")
        
        return all_players, players_data
        
    except Exception as e:
        print(f"  Error: {e}")
        return [], players_data


def display_projections(player_projections, round_name='', limit=300):
    """Display formatted projections"""
    print("\n" + "=" * 100)
    title = f"HALF PPR PROJECTIONS - {round_name.upper()}" if round_name else "HALF PPR PROJECTIONS"
    print(title)
    print("=" * 100)
    
    positions = {'QB': [], 'RB': [], 'WR': [], 'TE': [], 'WR/TE': [], 'FLEX': []}
    for player in player_projections:
        pos = player['position']
        if pos in positions:
            positions[pos].append(player)
        else:
            positions['FLEX'].append(player)
    
    # Combine WR and TE lists with WR/TE
    wr_te_combined = positions['WR'] + positions['TE'] + positions['WR/TE']
    wr_te_combined.sort(key=lambda x: x['half_ppr_points'], reverse=True)
    
    print(f"\n[TOP {min(50, len(player_projections))} OVERALL PROJECTIONS]")
    print("-" * 110)
    print(f"{'Rank':<5} {'Player':<25} {'Pos':<5} {'Team':<6} {'Pass':<8} {'Rush':<8} {'Rec':<8} {'Recep':<6} {'Pts':<8}")
    print("-" * 110)
    for i, p in enumerate(player_projections[:50], 1):
        team = p.get('team', p.get('game', '')[:5])
        print(f"{i:<5} {p['name']:<25} {p['position']:<5} {team:<6} {p['pass_yds']:<8.1f} {p['rush_yds']:<8.1f} {p['rec_yds']:<8.1f} {p['receptions']:<6.1f} {p['half_ppr_points']:<8.1f}")
    
    print(f"\n\n[QUARTERBACK PROJECTIONS - Top {min(20, len(positions['QB']))}]")
    print("-" * 90)
    print(f"{'Rank':<5} {'Player':<25} {'Team':<6} {'Pass Yds':<10} {'Pass TDs':<10} {'Pts':<8}")
    print("-" * 90)
    for i, p in enumerate(positions['QB'][:20], 1):
        team = p.get('team', '')
        print(f"{i:<5} {p['name']:<25} {team:<6} {p['pass_yds']:<10.1f} {p['pass_tds']:<10.1f} {p['half_ppr_points']:<8.1f}")
    
    print(f"\n\n[RUNNING BACK PROJECTIONS - Top {min(40, len(positions['RB']))}]")
    print("-" * 100)
    print(f"{'Rank':<5} {'Player':<25} {'Team':<6} {'Rush Yds':<10} {'Rec Yds':<10} {'Recep':<8} {'Pts':<8}")
    print("-" * 100)
    for i, p in enumerate(positions['RB'][:40], 1):
        team = p.get('team', '')
        print(f"{i:<5} {p['name']:<25} {team:<6} {p['rush_yds']:<10.1f} {p['rec_yds']:<10.1f} {p['receptions']:<8.1f} {p['half_ppr_points']:<8.1f}")
    
    print(f"\n\n[WIDE RECEIVER PROJECTIONS - Top {min(50, len(positions['WR']))}]")
    print("-" * 100)
    print(f"{'Rank':<5} {'Player':<25} {'Team':<6} {'Rec Yds':<10} {'Recep':<8} {'Pts':<8}")
    print("-" * 100)
    for i, p in enumerate(positions['WR'][:50], 1):
        team = p.get('team', '')
        print(f"{i:<5} {p['name']:<25} {team:<6} {p['rec_yds']:<10.1f} {p['receptions']:<8.1f} {p['half_ppr_points']:<8.1f}")
    
    print(f"\n\n[TIGHT END PROJECTIONS - Top {min(20, len(positions['TE']))}]")
    print("-" * 100)
    print(f"{'Rank':<5} {'Player':<25} {'Team':<6} {'Rec Yds':<10} {'Recep':<8} {'Pts':<8}")
    print("-" * 100)
    for i, p in enumerate(positions['TE'][:20], 1):
        team = p.get('team', '')
        print(f"{i:<5} {p['name']:<25} {team:<6} {p['rec_yds']:<10.1f} {p['receptions']:<8.1f} {p['half_ppr_points']:<8.1f}")
    
    print("\n\n[SUMMARY]")
    print("-" * 50)
    print(f"Total Players with Projections: {len(player_projections)}")
    print(f"  - Quarterbacks: {len(positions['QB'])}")
    print(f"  - Running Backs: {len(positions['RB'])}")
    print(f"  - Wide Receivers: {len(positions['WR'])}")
    print(f"  - Tight Ends: {len(positions['TE'])}")


def main():
    print("=" * 70)
    print("NFL PLAYOFFS - Half PPR Projections Calculator (All Rounds)")
    print("=" * 70)
    print()
    print("Fetching projections for all playoff rounds:")
    for week, info in PLAYOFF_WEEKS.items():
        method = "Weekly Projections" if info['use_weekly'] else "Season Average PPG"
        print(f"  - Week {week}: {info['name']} ({method})")
    print()
    
    # Cache for player database (avoid re-fetching for each week)
    players_cache = None
    season_averages_cache = None
    all_round_projections = {}
    
    # Loop through all playoff weeks
    for week, week_info in PLAYOFF_WEEKS.items():
        round_name = week_info['name']
        filename = week_info['filename']
        use_weekly = week_info['use_weekly']
        
        print("\n" + "-" * 70)
        print(f"Processing {round_name} (Week {week})")
        print("-" * 70)
        
        if use_weekly:
            # Use weekly projections for this round
            player_projections, players_cache = fetch_sleeper_projections(
                week=week,
                round_name=round_name,
                players_cache=players_cache
            )
        else:
            # Use season averages for this round
            if season_averages_cache is None:
                player_projections, players_cache = fetch_season_averages(
                    round_name=round_name,
                    players_cache=players_cache
                )
                season_averages_cache = player_projections
            else:
                # Reuse cached season averages, just update the round name
                player_projections = []
                for p in season_averages_cache:
                    player_copy = p.copy()
                    player_copy['game'] = f"{p['team']} ({round_name})"
                    player_projections.append(player_copy)
                print(f"\n  Using cached season averages for {round_name}")
        
        if not player_projections:
            print(f"\n  No projections available for {round_name}.")
            continue
        
        # Sort and limit to top 300
        player_projections.sort(key=lambda x: x['half_ppr_points'], reverse=True)
        player_projections = player_projections[:300]
        
        print(f"  Total players with projections: {len(player_projections)}")
        
        # Store for summary
        all_round_projections[round_name] = player_projections
        
        # Display top 10 for this round
        print(f"\n  Top 10 for {round_name}:")
        for i, p in enumerate(player_projections[:10], 1):
            print(f"    {i}. {p['name']} ({p['position']}, {p['team']}) - {p['half_ppr_points']:.1f} pts")
        
        # Export to CSV
        export_to_csv(player_projections, filename)
    
    # Final summary
    print("\n" + "=" * 70)
    print("SUMMARY - ALL PLAYOFF ROUNDS")
    print("=" * 70)
    
    for round_name, projections in all_round_projections.items():
        if projections:
            positions = {'QB': 0, 'RB': 0, 'WR': 0, 'TE': 0}
            for p in projections:
                if p['position'] in positions:
                    positions[p['position']] += 1
            print(f"\n{round_name}:")
            print(f"  Total: {len(projections)} players")
            print(f"  QB: {positions['QB']}, RB: {positions['RB']}, WR: {positions['WR']}, TE: {positions['TE']}")
            print(f"  Top scorer: {projections[0]['name']} ({projections[0]['half_ppr_points']:.1f} pts)")
    
    print("\n" + "=" * 70)
    print("CSV FILES GENERATED:")
    print("=" * 70)
    for week_info in PLAYOFF_WEEKS.values():
        print(f"  - {week_info['filename']}")
    
    return all_round_projections


if __name__ == '__main__':
    main()
