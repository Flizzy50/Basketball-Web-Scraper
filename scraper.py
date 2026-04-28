"""Scrape NBA player game-by-game stats from Basketball Reference."""

import argparse
import re
import sys
from io import StringIO

import cloudscraper
import pandas as pd
from bs4 import BeautifulSoup

BASE_URL = "https://www.basketball-reference.com"
TEAM_NAMES = {
    "ATL": "Hawks", "BOS": "Celtics", "BRK": "Nets", "CHO": "Hornets",
    "CHI": "Bulls", "CLE": "Cavaliers", "DAL": "Mavericks", "DEN": "Nuggets",
    "DET": "Pistons", "GSW": "Warriors", "HOU": "Rockets", "IND": "Pacers",
    "LAC": "Clippers", "LAL": "Lakers", "MEM": "Grizzlies", "MIA": "Heat",
    "MIL": "Bucks", "MIN": "Timberwolves", "NOP": "Pelicans", "NYK": "Knicks",
    "OKC": "Thunder", "ORL": "Magic", "PHI": "76ers", "PHO": "Suns",
    "POR": "Trail Blazers", "SAC": "Kings", "SAS": "Spurs", "TOR": "Raptors",
    "UTA": "Jazz", "WAS": "Wizards",
    # Historical
    "NJN": "Nets", "CHH": "Hornets", "SEA": "SuperSonics", "VAN": "Grizzlies",
    "WSB": "Bullets", "NOH": "Hornets", "NOK": "Hornets", "CHA": "Bobcats",
}


def make_player_id(name: str) -> str:
    """Build Basketball Reference player ID from a name (best-effort first guess).

    Format: first 5 letters of last name + first 2 letters of first name + '01'.
    e.g. 'LeBron James' -> 'jamesle01'.
    """
    cleaned = re.sub(r"[^a-zA-Z\s]", "", name).strip().lower().split()
    if len(cleaned) < 2:
        raise ValueError("Please provide both first and last name.")
    first, last = cleaned[0], cleaned[-1]
    return f"{last[:5]}{first[:2]}01"


def fetch_page(scraper, url: str) -> str | None:
    """GET a page; return text on 200, None on 404."""
    resp = scraper.get(url, timeout=30)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.text


def resolve_player(scraper, name: str) -> tuple[str, str]:
    """Find a player's ID and canonical name using BR's search."""
    # Try the deterministic ID first
    pid_guess = make_player_id(name)
    url = f"{BASE_URL}/players/{pid_guess[0]}/{pid_guess}.html"
    html = fetch_page(scraper, url)
    if html:
        soup = BeautifulSoup(html, "lxml")
        h1 = soup.find("h1")
        canonical = h1.get_text(strip=True) if h1 else name
        return pid_guess, canonical

    # Fall back to BR search
    search_url = f"{BASE_URL}/search/search.fcgi?search={name.replace(' ', '+')}"
    resp = scraper.get(search_url, timeout=30, allow_redirects=True)
    resp.raise_for_status()
    final = resp.url
    match = re.search(r"/players/[a-z]/([a-z]+\d{2})\.html", final)
    if match:
        pid = match.group(1)
        soup = BeautifulSoup(resp.text, "lxml")
        h1 = soup.find("h1")
        canonical = h1.get_text(strip=True) if h1 else name
        return pid, canonical

    soup = BeautifulSoup(resp.text, "lxml")
    first_hit = soup.select_one("div.search-item-name a[href*='/players/']")
    if first_hit:
        href = first_hit["href"]
        match = re.search(r"/players/[a-z]/([a-z]+\d{2})\.html", href)
        if match:
            return match.group(1), first_hit.get_text(strip=True)

    raise LookupError(f"Could not find a Basketball Reference page for '{name}'.")


def latest_season(scraper, player_id: str) -> int:
    """Read the player's profile to find the most recent season they played."""
    url = f"{BASE_URL}/players/{player_id[0]}/{player_id}.html"
    html = fetch_page(scraper, url)
    if not html:
        raise LookupError(f"No profile page for {player_id}")
    soup = BeautifulSoup(html, "lxml")
    years = []
    for th in soup.select("table#per_game_stats tbody th[data-stat='year_id']"):
        a = th.find("a")
        text = a.get_text(strip=True) if a else th.get_text(strip=True)
        m = re.match(r"(\d{4})-\d{2}", text)
        if m:
            years.append(int(m.group(1)) + 1)  # season label uses end year
    if not years:
        # Fall back: any year-looking text on the profile
        for el in soup.select("[data-stat='year_id']"):
            m = re.search(r"(\d{4})-\d{2}", el.get_text())
            if m:
                years.append(int(m.group(1)) + 1)
    if not years:
        raise LookupError("Could not determine latest season from profile.")
    return max(years)


def fetch_game_log(scraper, player_id: str, season: int) -> pd.DataFrame:
    """Pull the regular-season game log table for a (player, season)."""
    url = f"{BASE_URL}/players/{player_id[0]}/{player_id}/gamelog/{season}"
    html = fetch_page(scraper, url)
    if not html:
        raise LookupError(f"No game log found for {player_id} in {season}.")

    table_ids = ("player_game_log_reg", "pgl_basic")
    soup = BeautifulSoup(html, "lxml")
    table = next((soup.find("table", id=tid) for tid in table_ids if soup.find("table", id=tid)), None)
    if table is None:
        # BR occasionally hides tables inside HTML comments.
        from bs4 import Comment
        for c in soup.find_all(string=lambda t: isinstance(t, Comment)):
            if any(tid in c for tid in table_ids):
                inner = BeautifulSoup(c, "lxml")
                for tid in table_ids:
                    table = inner.find("table", id=tid)
                    if table is not None:
                        break
                if table is not None:
                    break
    if table is None:
        raise LookupError(f"Game log table not present on page for {season}.")

    return pd.read_html(StringIO(str(table)))[0]


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Pick out the columns we care about and clean them up."""
    # Column names vary slightly by season; map known aliases.
    rename = {"Date": "Date", "Opp": "Opp", "MP": "MP",
              "PTS": "PTS", "AST": "AST", "TRB": "TRB"}
    df = df.rename(columns=rename)

    keep = ["Date", "Opp", "MP", "PTS", "AST", "TRB"]
    missing = [c for c in keep if c not in df.columns]
    if missing:
        raise LookupError(f"Game log missing expected columns: {missing}")
    out = df[keep].copy()

    # Drop season-summary rows (no Date) and inactive/DNP rows (non-numeric PTS).
    out = out[out["Date"].astype(str).str.match(r"\d{4}-\d{2}-\d{2}")].copy()
    out = out[pd.to_numeric(out["PTS"], errors="coerce").notna()].copy()
    out["PTS"] = out["PTS"].astype(int)
    out["AST"] = out["AST"].astype(int)
    out["TRB"] = out["TRB"].astype(int)
    out["Opponent"] = out["Opp"].map(lambda code: TEAM_NAMES.get(code, code))
    return out.reset_index(drop=True)


def print_games(player_name: str, games: pd.DataFrame, limit: int | None) -> None:
    rows = games if limit is None else games.tail(limit)
    if rows.empty:
        print("No games to display.")
        return
    for _, g in rows.iterrows():
        print(f"Player: {player_name}")
        print(f"Date: {g['Date']}")
        print(f"Opponent: {g['Opponent']}")
        print(f"Points: {g['PTS']}")
        print(f"Assists: {g['AST']}")
        print(f"Rebounds: {g['TRB']}")
        print(f"Minutes: {g['MP']}")
        print()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Scrape NBA player game logs from Basketball Reference."
    )
    p.add_argument("player", nargs="*", help="Player name, e.g. 'LeBron James'")
    p.add_argument("--season", type=int, default=None,
                   help="Season end year (e.g. 2024 for 2023-24). Defaults to latest.")
    p.add_argument("--limit", type=int, default=10,
                   help="How many of the most recent games to print (default 10). Use 0 for all.")
    return p.parse_args()


def main() -> int:
    # Windows console defaults to cp1252; many player names have accents.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    args = parse_args()
    name = " ".join(args.player) if args.player else input("Player name: ").strip()
    if not name:
        print("No player name given.", file=sys.stderr)
        return 2

    scraper = cloudscraper.create_scraper(
        browser={"browser": "chrome", "platform": "windows", "mobile": False}
    )

    try:
        player_id, canonical = resolve_player(scraper, name)
        season = args.season or latest_season(scraper, player_id)
        raw = fetch_game_log(scraper, player_id, season)
        games = normalize(raw)
    except (LookupError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    print(f"=== {canonical} - {season - 1}-{str(season)[-2:]} regular season ===\n")
    print_games(canonical, games, None if args.limit == 0 else args.limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
