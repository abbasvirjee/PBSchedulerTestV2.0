from flask import Flask, render_template, request, jsonify
import itertools
import random

app = Flask(__name__)

# Global variables to store the game data
game_count = {}
player_names = []
previous_fixtures = []
team_opponents = {}



@app.route('/', methods=['GET', 'POST'])
@app.route('/home', methods=['GET', 'POST'])
def home():
    if request.method == 'POST':
        global player_names, game_count, previous_fixtures, team_opponents
        num_players = int(request.form['num_players'])
        player_names = [request.form[f'player_{i + 1}'] for i in range(num_players)]
        game_count = {player: 0 for player in player_names}  # Reset game count
        previous_fixtures = []
        # Initialize team_opponents with all possible pairs of players
        team_opponents = {frozenset(pair): set() for pair in itertools.combinations(player_names, 2)}
        return render_template('home.html', num_players=num_players)
    return render_template('home.html')


@app.route('/submit_players', methods=['POST'])
def submit_players():
    global player_names
    num_players = int(request.form['num_players'])
    player_names = [request.form[f'player_{i + 1}'] for i in range(num_players)]
    return jsonify(player_names=player_names)


@app.route('/fixtures', methods=['GET'])
def fixtures():
    global player_names, game_count
    player_names = request.args.get('player_names').split(',')

    # Ensure game_count is updated with new player names
    game_count = {player: game_count.get(player, 0) for player in player_names}

    # Generate initial fixtures
    fixtures = generate_fixtures(player_names, game_count)

    # Pass the game_count to the template
    return render_template('fixtures.html', fixtures=fixtures, game_count=game_count)


@app.route('/add_game', methods=['POST'])
def add_game():
    global player_names, game_count
    # Try to generate a unique game
    new_game = generate_single_game(player_names, game_count)

    # If no unique game is possible, generate a fallback game
    if not new_game:
        fallback_game = generate_fallback_game(player_names, game_count)
        if fallback_game:
            return jsonify(
                success=True,
                new_fixture=fallback_game,
                game_count=game_count,
                fallback=True,
                message="Adding more games cannot ensure uniqueness."
            )
        else:
            return jsonify(success=False, message="Unable to generate any more games"), 400

    # Return both the new fixture and updated game count
    return jsonify(
        success=True,
        new_fixture=new_game,
        game_count=game_count  # Send the updated game count
    )

def generate_fallback_game(player_names, game_count):
    random.shuffle(player_names)
    pairs = list(itertools.combinations(player_names, 2))

    team1, team2 = None, None
    for pair in pairs:
        # Fallback: Select any two valid teams, even if they've played before
        if team1 is None:
            team1 = pair
        elif team2 is None and not set(pair) & set(team1):
            team2 = pair
            break

    # If valid teams cannot be selected, return None
    if not team1 or not team2:
        return None

    # Increment game counts
    for player in team1 + team2:
        game_count[player] += 1

    # Return the new game
    game_number = len(previous_fixtures) + 1
    new_game = {"game_number": game_number, "teams": [team1, team2]}
    previous_fixtures.append(new_game)

    return new_game



def generate_fixtures(player_names, game_count):
    random.shuffle(player_names)  # Shuffle to ensure random pairing
    fixtures = []
    unique_teams = set()  # Track unique pairs of players
    game_number = len(previous_fixtures) + 1  # Start the game numbering from the total count
    total_players = len(player_names)

    # Calculate the total number of unique games required: Each player plays with every other player once
    required_unique_pairs = set(itertools.combinations(player_names, 2))  # All unique pairs of players

    # Continue generating fixtures until all pairs are played and players have equal games
    while True:
        team1, team2 = select_teams(player_names, game_count, unique_teams)

        # If no valid teams can be formed, break the loop
        if not team1 or not team2:
            break

        # Add the fixture with the game number
        fixtures.append({
            "game_number": game_number,
            "teams": [team1, team2]
        })

        # Update the set of unique teams
        unique_teams.add(frozenset(team1))
        unique_teams.add(frozenset(team2))

        # Increment the game count for each player
        for player in team1 + team2:
            game_count[player] += 1

        # Increment game number for each new game
        game_number += 1

        # Check if all players have equal games
        if len(set(game_count.values())) == 1:
            # Check if all pairs have played
            if required_unique_pairs == unique_teams:
                break  # Stop generating games if both conditions are satisfied

    previous_fixtures.extend(fixtures)  # Save the fixtures for future reference
    return fixtures


def select_teams(player_names, game_count, unique_teams, max_games=2):
    pairs = list(itertools.combinations(player_names, 2))  # Generate pairs within the function
    # Sort pairs by total number of games played
    pairs = sorted(pairs, key=lambda p: game_count[p[0]] + game_count[p[1]])
    team1 = team2 = None

    # Try finding teams that haven't played together first
    for pair in pairs:
        if frozenset(pair) not in unique_teams and not has_played_together(pair, max_games):
            team1 = pair
            break

    # If no unique team1 is found, allow repeated team pairings with fallback logic
    if not team1:
        for pair in pairs:
            if frozenset(pair) not in unique_teams and can_repeat(pair, 2):  # Allow repeating after 2 games
                team1 = pair
                break

    # If no team1 could be selected, return None to stop generating games
    if not team1:
        return None, None

    # Try finding a valid opponent for team1
    for pair in pairs:
        if frozenset(pair) not in unique_teams and not set(team1) & set(pair) and not has_faced_opponent(team1, pair):
            team2 = pair
            break

    # If no unique opponent is found, allow repeated opponents with fallback
    if not team2:
        for pair in pairs:
            if frozenset(pair) not in unique_teams and not set(team1) & set(pair) and can_repeat_opponents(pair, team1):
                team2 = pair
                break

    # If no valid teams can be formed, return None
    if not team1 or not team2:
        return None, None

    # Record opponent information for both teams
    team_opponents[frozenset(team1)].add(frozenset(team2))
    team_opponents[frozenset(team2)].add(frozenset(team1))

    return team1, team2

def can_repeat(pair, min_games):
    return all(game_count[player] >= min_games for player in pair)

def can_repeat_opponents(team1, team2):
    return frozenset(team1) not in team_opponents or len(team_opponents[frozenset(team1)]) >= len(list(itertools.combinations(player_names, 2))) - 1


def has_played_together(pair, max_games):
    play_count = 0
    for fixture in previous_fixtures:
        if frozenset(pair) in map(frozenset, fixture["teams"]):
            play_count += 1
        if play_count >= max_games:
            return True
    return False


def has_faced_opponent(team1, team2):
    if frozenset(team1) not in team_opponents:
        team_opponents[frozenset(team1)] = set()
    if frozenset(team2) not in team_opponents:
        team_opponents[frozenset(team2)] = set()

    # Ensure teams haven't faced each other too many times before
    return frozenset(team2) in team_opponents[frozenset(team1)]


def generate_single_game(player_names, game_count):
    random.shuffle(player_names)
    unique_teams = set()

    # Sort pairs by the total number of games played
    pairs = sorted(list(itertools.combinations(player_names, 2)), key=lambda p: game_count[p[0]] + game_count[p[1]])

    # Select valid teams ensuring no repeat back-to-back
    team1, team2 = select_teams(player_names, game_count, unique_teams)
    if not team1 or not team2 or set(team1) & set(team2):
        return None

    # Update game count
    for player in team1 + team2:
        game_count[player] += 1

    game_number = len(previous_fixtures) + 1
    new_game = {"game_number": game_number, "teams": [team1, team2]}
    previous_fixtures.append(new_game)

    return new_game


@app.route('/save_scores', methods=['POST'])
def save_scores():
    global previous_fixtures

    scores = request.json.get('scores', {})  # Get the scores from the frontend

    # Initialize dictionaries to store games won and points difference
    games_won = {player: 0 for player in player_names}
    points_diff = {player: 0 for player in player_names}

    # Loop over previous fixtures and update stats
    for fixture in previous_fixtures:
        game_number = fixture['game_number']
        score1 = scores.get(f'score1-{game_number}', None)
        score2 = scores.get(f'score2-{game_number}', None)

        if score1 is not None and score2 is not None:
            score1 = int(score1)
            score2 = int(score2)

            team1 = fixture['teams'][0]
            team2 = fixture['teams'][1]

            if score1 > score2:
                # Team1 wins
                for player in team1:
                    games_won[player] += 1
                    points_diff[player] += (score1 - score2)
                for player in team2:
                    points_diff[player] -= (score1 - score2)
            elif score2 > score1:
                # Team2 wins
                for player in team2:
                    games_won[player] += 1
                    points_diff[player] += (score2 - score1)
                for player in team1:
                    points_diff[player] -= (score2 - score1)

    # Create a list of players and sort by games won and points difference
    sorted_players = sorted(games_won.keys(), key=lambda player: (games_won[player], points_diff[player]), reverse=True)

    # Convert sorted data into a list of dictionaries to return in the correct order
    sorted_data = [
        {
            "player": player,
            "games_won": games_won[player],
            "points_diff": points_diff[player],
            "games_played": game_count[player]
        }
        for player in sorted_players
    ]

    # Return the sorted games won and points difference
    return jsonify(sorted_data=sorted_data)

@app.route('/delete_last_game', methods=['POST'])
def delete_last_game():
    global previous_fixtures, game_count

    if previous_fixtures:
        # Remove the last game from previous fixtures
        last_game = previous_fixtures.pop()

        # Update the game count by subtracting the players' games from the removed fixture
        for player in last_game['teams'][0] + last_game['teams'][1]:
            game_count[player] -= 1

    # Return the updated game count to the frontend
    return jsonify(success=True, game_count=game_count)


@app.route('/save_final_score', methods=['POST'])
def save_final_score():
    data = request.json
    score1 = int(data.get('score1', 0))
    score2 = int(data.get('score2', 0))
    team1 = data.get('team1', [])
    team2 = data.get('team2', [])

    # Ensure team1 and team2 both have exactly two players
    if len(team1) != 2 or len(team2) != 2:
        return jsonify(success=False, message="Error: Teams must have two players each.")

    # Determine the winner based on the scores
    if score1 > score2:
        winner = f"Congratulations to {team1[0]} & {team1[1]}"
    elif score2 > score1:
        winner = f"Congratulations to {team2[0]} & {team2[1]}"
    else:
        winner = "It's a tie!"

    return jsonify(success=True, winner=winner)


if __name__ == '__main__':
    app.run(debug=True)