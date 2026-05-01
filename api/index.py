from flask import Flask, request, jsonify, render_template
import random
import os
from copy import deepcopy

app = Flask(__name__, template_folder='../templates')

def adjacent_cells(r, c, rows, cols):
    for dr, dc in [(1,0),(-1,0),(0,1),(0,-1)]:
        nr, nc = r+dr, c+dc
        if 0 <= nr < rows and 0 <= nc < cols:
            yield (nr, nc)

def infer_safe_and_hazards(visited, percept_history, rows, cols):
    potential_pits = set()
    potential_wumpus = set()
    visited_set = set(tuple(v) for v in visited)

    for (r,c), percepts in percept_history.items():
        if 'Breeze' in percepts:
            for nr, nc in adjacent_cells(r, c, rows, cols):
                if (nr, nc) not in visited_set:
                    potential_pits.add((nr, nc))
        if 'Stench' in percepts:
            for nr, nc in adjacent_cells(r, c, rows, cols):
                if (nr, nc) not in visited_set:
                    potential_wumpus.add((nr, nc))

    safe = [list(cell) for cell in visited_set]
    for r in range(rows):
        for c in range(cols):
            cell = (r,c)
            if cell not in visited_set:
                if cell not in potential_pits and cell not in potential_wumpus:
                    safe.append([r,c])

    confirmed = []
    for (r,c), percepts in percept_history.items():
        if 'Breeze' in percepts:
            unvisited = [(nr,nc) for (nr,nc) in adjacent_cells(r,c,rows,cols) if (nr,nc) not in visited_set]
            if len(unvisited) == 1:
                confirmed.append(unvisited[0])
    for (r,c), percepts in percept_history.items():
        if 'Stench' in percepts:
            unvisited = [(nr,nc) for (nr,nc) in adjacent_cells(r,c,rows,cols) if (nr,nc) not in visited_set]
            if len(unvisited) == 1:
                confirmed.append(unvisited[0])

    confirmed = [list(c) for c in set(confirmed)]
    return safe, confirmed

# ------------------ Routes ------------------
@app.route('/')
def index():
    try:
        return render_template('index.html')
    except Exception as e:
        return f"<h1>Template error</h1><p>{str(e)}</p>", 500

@app.route('/api/new', methods=['POST'])
def new_game():
    try:
        data = request.get_json()
        rows = data.get('rows', 5)
        cols = data.get('cols', 5)

        # Generate random world
        pits = []
        while len(pits) < max(1, int(rows*cols*0.12)):
            r = random.randint(0, rows-1)
            c = random.randint(0, cols-1)
            if (r,c) != (0,0) and [r,c] not in pits:
                pits.append([r,c])

        wumpus = [random.randint(0, rows-1), random.randint(0, cols-1)]
        while wumpus == [0,0] or wumpus in pits:
            wumpus = [random.randint(0, rows-1), random.randint(0, cols-1)]

        gold = [random.randint(0, rows-1), random.randint(0, cols-1)]
        while gold == [0,0] or gold in pits or gold == wumpus:
            gold = [random.randint(0, rows-1), random.randint(0, cols-1)]

        # Initial percepts at (0,0)
        r,c = 0,0
        percepts = []
        for pr, pc in pits:
            if abs(pr-r) + abs(pc-c) == 1:
                percepts.append("Breeze")
                break
        if abs(wumpus[0]-r) + abs(wumpus[1]-c) == 1:
            percepts.append("Stench")
        if [r,c] == gold:
            percepts.append("Glitter")

        game_state = {
            'status': 'playing',
            'rows': rows,
            'cols': cols,
            'agent': [0,0],
            'visited': [[0,0]],
            'safe_cells': [[0,0]],
            'pits': pits,
            'wumpus': wumpus,
            'gold': gold,
            'confirmed_hazards': [],
            'percepts': percepts,
            'log': ["Game started. Agent at (0,0)"],
            'score': 0,
            'total_steps': 0,
            'kb_clauses': []
        }
        game_state['_percept_history'] = {(0,0): percepts}
        return jsonify(game_state)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/step', methods=['POST'])
def step():
    try:
        state = request.get_json()
        rows, cols = state['rows'], state['cols']
        agent = state['agent']
        visited = [tuple(v) for v in state['visited']]
        percept_history = {tuple(map(int,k.split(','))): v for k,v in state.get('_percept_history', {}).items()}
        percept_history[tuple(agent)] = state['percepts']

        safe_cells, confirmed_hazards = infer_safe_and_hazards(visited, percept_history, rows, cols)

        # Choose next move
        unvisited_safe = [cell for cell in safe_cells if tuple(cell) not in visited]
        possible = []
        for dr, dc in [(1,0),(-1,0),(0,1),(0,-1)]:
            nr, nc = agent[0]+dr, agent[1]+dc
            if 0 <= nr < rows and 0 <= nc < cols and [nr,nc] in unvisited_safe:
                possible.append([nr,nc])
        if possible:
            new_agent = possible[0]
        elif unvisited_safe:
            new_agent = unvisited_safe[0]
        else:
            new_agent = agent

        new_state = deepcopy(state)
        new_state['agent'] = new_agent
        if tuple(new_agent) not in visited:
            new_state['visited'].append(new_agent)
        new_state['safe_cells'] = safe_cells
        new_state['confirmed_hazards'] = confirmed_hazards
        new_state['total_steps'] = state.get('total_steps', 0) + 1

        # Check termination
        if new_agent == state['gold']:
            new_state['status'] = 'won'
            new_state['score'] = state['score'] + 1000
            new_state['log'].append("💰 Gold collected! Victory!")
        elif new_agent in state['pits'] or new_agent == state['wumpus']:
            new_state['status'] = 'dead'
            new_state['score'] = state['score'] - 1000
            new_state['log'].append("💀 Agent died!")
        else:
            new_state['score'] = state['score'] - 1
            new_state['log'].append(f"Moved to {new_agent}")

        # New percepts
        r,c = new_agent
        new_percepts = []
        for pr, pc in state['pits']:
            if abs(pr-r) + abs(pc-c) == 1:
                new_percepts.append("Breeze")
                break
        if abs(state['wumpus'][0]-r) + abs(state['wumpus'][1]-c) == 1:
            new_percepts.append("Stench")
        if new_agent == state['gold']:
            new_percepts.append("Glitter")
        new_state['percepts'] = new_percepts

        percept_history[tuple(new_agent)] = new_percepts
        new_state['_percept_history'] = {f"{k[0]},{k[1]}": v for k,v in percept_history.items()}
        new_state['kb_clauses'] = []

        if new_state['status'] != 'playing':
            new_state['log'].append(f"Game ended: {new_state['status']}")

        return jsonify(new_state)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)