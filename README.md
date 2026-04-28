# Basketball Web Scraper

A small command-line tool that scrapes any NBA player's game-by-game statistics
from [Basketball Reference](https://www.basketball-reference.com/) and prints
them in a clean format in your terminal.

For each game it shows the **date, opponent, points, assists, rebounds, and minutes played**.

## Requirements

- Python **3.10+** (uses `str | None` type syntax)
- Internet access (the scraper hits basketball-reference.com live)

## Setup

```bash
# 1. Clone the repo
git clone https://github.com/Flizzy50/Basketball-Web-Scraper.git
cd Basketball-Web-Scraper

# 2. Create a virtual environment
python -m venv .venv

# 3. Activate it
#    Windows (PowerShell):
.venv\Scripts\Activate.ps1
#    Windows (Git Bash / WSL):
source .venv/Scripts/activate
#    macOS / Linux:
source .venv/bin/activate

# 4. Install dependencies
pip install -r requirements.txt
```

## Usage

```bash
python scraper.py "<Player Name>" [--season YEAR] [--limit N]
```

| Flag        | Description                                                                                  | Default      |
| ----------- | -------------------------------------------------------------------------------------------- | ------------ |
| `player`    | Full player name (positional). Quote it if it contains a space.                              | *(required)* |
| `--season`  | Season **end year** (e.g. `2024` for the 2023-24 season).                                    | latest       |
| `--limit`   | How many of the **most recent** games to print. Use `0` to print every game in the season.   | `10`         |

If you run `python scraper.py` with no player name, it will prompt you for one.

### Examples

```bash
# Latest season, last 10 games
python scraper.py "LeBron James"

# Specific season, last 5 games
python scraper.py "Stephen Curry" --season 2024 --limit 5

# Every game of the season
python scraper.py "Nikola Jokic" --limit 0
```

### Sample output

```
=== LeBron James - 2025-26 regular season ===

Player: LeBron James
Date: 2026-04-09
Opponent: Warriors
Points: 26
Assists: 11
Rebounds: 8
Minutes: 31:48

Player: LeBron James
Date: 2026-04-10
Opponent: Suns
Points: 28
Assists: 12
Rebounds: 6
Minutes: 32:06
```

## How it works

1. Resolves the player name to a Basketball Reference player ID
   (`LeBron James` → `jamesle01`). If the deterministic guess 404s, it falls
   back to BR's search endpoint.
2. Looks up the player's most recent season from their profile page (unless
   `--season` is provided).
3. Fetches the game-log page (`/players/<x>/<id>/gamelog/<season>`) using
   [`cloudscraper`](https://pypi.org/project/cloudscraper/) so it can get past
   Cloudflare.
4. Parses the `player_game_log_reg` table with BeautifulSoup +
   `pandas.read_html`, drops summary and DNP rows, and maps team codes to
   readable names (`GSW` → `Warriors`).
5. Prints the requested number of most recent games.

## Notes & limitations

- **Regular season only.** Playoff games live in a separate table
  (`player_game_log_post`) and are not included.
- **Inactive / DNP games are dropped.** If a player didn't play, that row
  is filtered out.
- **Be polite.** Basketball Reference asks scrapers to keep traffic light
  (≤ 20 requests/minute, see their
  [robots.txt and ToS](https://www.sports-reference.com/data_use.html)).
  This tool makes 1–2 requests per invocation; don't put it in a tight loop.
- **Player ID guessing.** The first-pass ID is built as
  `<first 5 letters of last name><first 2 letters of first name>01`. This is
  correct for the vast majority of players but not all (e.g. duplicate names
  use `02`, `03`, …). The search-endpoint fallback handles those cases.
- **Windows console.** The script forces stdout to UTF-8 so accented names
  (Jokić, Dončić, …) print correctly.

## Project structure

```
Basketball-Web-Scraper/
├── README.md
├── requirements.txt
└── scraper.py
```
