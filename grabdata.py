import os
from dotenv import load_dotenv
import requests

# Load variables from .env into the environment
load_dotenv()

# Access the key
api_key = os.getenv('THE_ODDS_API_KEY')

if not api_key:
    raise ValueError("API Key not found. Ensure it is set in your .env file.")

SPORT = 'americanfootball_nfl'
REGIONS = 'us'
MARKETS = 'player_pass_yds,player_rush_yds,player_anytime_td' # Specific props

# 1. Get Event IDs for the Wild Card games
events_url = f'https://api.the-odds-api.com/v4/sports/{SPORT}/events?apiKey={api_key}'
events = requests.get(events_url).json()

# 2. Grab props for a specific game (e.g., Rams @ Panthers)
# Note: You'd loop through event IDs in a real script
event_id = events[0]['id'] 
props_url = f'https://api.the-odds-api.com/v4/sports/{SPORT}/events/{event_id}/odds?apiKey={api_key}&regions={REGIONS}&markets={MARKETS}'

data = requests.get(props_url).json()
print(data)