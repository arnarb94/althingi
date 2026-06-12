"""Les XML úr etl/cache/ og byggir SQLite-gagnagrunn (data/althingi.db)."""
import sqlite3
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

CACHE = Path(__file__).parent / "cache"
DB = Path(__file__).parent.parent / "data" / "althingi.db"

SCHEMA = """
DROP TABLE IF EXISTS sessions;
DROP TABLE IF EXISTS parties;
DROP TABLE IF EXISTS members;
DROP TABLE IF EXISTS seats;
DROP TABLE IF EXISTS votes;
DROP TABLE IF EXISTS vote_casts;
DROP TABLE IF EXISTS speeches;

CREATE TABLE sessions (num INTEGER PRIMARY KEY, period TEXT, start TEXT, end TEXT);
CREATE TABLE parties (id INTEGER PRIMARY KEY, name TEXT, abbr_short TEXT, abbr_long TEXT);
CREATE TABLE members (id INTEGER PRIMARY KEY, name TEXT, birth TEXT, abbr TEXT);
CREATE TABLE seats (
  member_id INTEGER, lthing INTEGER, type TEXT,
  party_id INTEGER, party_name TEXT,
  constituency_id INTEGER, constituency TEXT,
  date_in TEXT, date_out TEXT
);
CREATE TABLE votes (
  num INTEGER PRIMARY KEY, lthing INTEGER, issue_num INTEGER, issue_class TEXT,
  issue_name TEXT, time TEXT, type TEXT, type_text TEXT, method TEXT,
  yes INTEGER, no INTEGER, abstain INTEGER, result TEXT
);
CREATE TABLE vote_casts (vote_num INTEGER, member_id INTEGER, vote TEXT);
CREATE TABLE speeches (
  member_id INTEGER, lthing INTEGER, date TEXT, start TEXT, end TEXT,
  seconds INTEGER, type TEXT, issue_name TEXT, role TEXT
);
CREATE INDEX idx_casts_vote ON vote_casts(vote_num);
CREATE INDEX idx_casts_member ON vote_casts(member_id);
CREATE INDEX idx_speeches_member ON speeches(member_id, lthing);
CREATE INDEX idx_seats_member ON seats(member_id, lthing);
CREATE INDEX idx_votes_lthing ON votes(lthing);
"""


def text(el, tag):
    t = el.find(tag)
    return t.text.strip() if t is not None and t.text else None


def load_sessions(con, first, last):
    root = ET.parse(CACHE / "loggjafarthing.xml").getroot()
    for el in root.iter("þing"):
        num = int(el.get("númer"))
        if first <= num <= last:
            con.execute(
                "INSERT INTO sessions VALUES (?,?,?,?)",
                (num, text(el, "tímabil"), text(el, "þingsetning"), text(el, "þinglok")),
            )


def load_parties(con):
    root = ET.parse(CACHE / "thingflokkar.xml").getroot()
    for el in root.iter("þingflokkur"):
        name = text(el, "heiti")
        con.execute(
            "INSERT OR REPLACE INTO parties VALUES (?,?,?,?)",
            (
                int(el.get("id")),
                name,
                text(el, "skammstafanir/stuttskammstöfun"),
                text(el, "skammstafanir/löngskammstöfun"),
            ),
        )


def load_members(con, first, last):
    seen = set()
    for lthing in range(first, last + 1):
        f = CACHE / str(lthing) / "thingmenn.xml"
        if not f.exists():
            continue
        for el in ET.parse(f).getroot().iter("þingmaður"):
            mid = int(el.get("id"))
            if mid in seen:
                continue
            seen.add(mid)
            con.execute(
                "INSERT OR REPLACE INTO members VALUES (?,?,?,?)",
                (mid, text(el, "nafn"), text(el, "fæðingardagur"), text(el, "skammstöfun")),
            )
    return seen


def load_seats(con, member_ids, first, last):
    for mid in member_ids:
        f = CACHE / "thingmenn" / f"thingseta_{mid}.xml"
        if not f.exists():
            continue
        for el in ET.parse(f).getroot().iter("þingseta"):
            if el.find("þing") is None:
                continue
            lthing = int(text(el, "þing"))
            if not (first <= lthing <= last):
                continue
            fl = el.find("þingflokkur")
            kj = el.find("kjördæmi")
            con.execute(
                "INSERT INTO seats VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    mid,
                    lthing,
                    text(el, "tegund"),
                    int(fl.get("id")) if fl is not None and fl.get("id") else None,
                    fl.text.strip() if fl is not None and fl.text else None,
                    int(kj.get("id")) if kj is not None and kj.get("id") else None,
                    "".join(kj.itertext()).strip() if kj is not None else None,
                    text(el, "tímabil/inn"),
                    text(el, "tímabil/út"),
                ),
            )


def load_votes(con, first, last):
    for lthing in range(first, last + 1):
        d = CACHE / str(lthing) / "atkv"
        if not d.exists():
            continue
        for f in sorted(d.glob("*.xml")):
            try:
                root = ET.parse(f).getroot()
            except ET.ParseError:
                print(f"  gallað xml: {f}", file=sys.stderr)
                continue
            num = int(root.get("atkvæðagreiðslunúmer"))
            nid = root.find("niðurstaða")
            teg = root.find("tegund")
            mal = root.find("mál")
            con.execute(
                "INSERT OR REPLACE INTO votes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    num,
                    lthing,
                    int(root.get("málsnúmer")) if root.get("málsnúmer") else None,
                    root.get("málsflokkur"),
                    text(mal, "málsheiti") if mal is not None else None,
                    text(root, "tími"),
                    teg.get("tegund") if teg is not None else None,
                    teg.text.strip() if teg is not None and teg.text else None,
                    text(nid, "aðferð") if nid is not None else text(root, "samantekt/aðferð"),
                    int(text(nid, "já/fjöldi") or 0) if nid is not None else None,
                    int(text(nid, "nei/fjöldi") or 0) if nid is not None else None,
                    int(text(nid, "greiðirekkiatkvæði/fjöldi") or 0) if nid is not None else None,
                    text(nid, "niðurstaða") if nid is not None else None,
                ),
            )
            skra = root.find("atkvæðaskrá")
            if skra is not None:
                con.executemany(
                    "INSERT INTO vote_casts VALUES (?,?,?)",
                    [
                        (num, int(m.get("id")), text(m, "atkvæði"))
                        for m in skra.iter("þingmaður")
                    ],
                )


def parse_role(rm):
    for tag in ("forsetiAlþingis", "ráðherra", "forsetiÍslands"):
        t = rm.find(tag)
        if t is not None and t.text:
            return t.text.strip()
    return None


def load_speeches(con, first, last):
    for lthing in range(first, last + 1):
        f = CACHE / str(lthing) / "raedulisti.xml"
        if not f.exists():
            continue
        rows = []
        for el in ET.parse(f).getroot().iter("ræða"):
            rm = el.find("ræðumaður")
            if rm is None or not rm.get("id"):
                continue
            start, end = text(el, "ræðahófst"), text(el, "ræðulauk")
            secs = None
            if start and end:
                try:
                    secs = int(
                        (
                            datetime.fromisoformat(end) - datetime.fromisoformat(start)
                        ).total_seconds()
                    )
                    if secs < 0:
                        secs = None
                except ValueError:
                    pass
            rows.append(
                (
                    int(rm.get("id")),
                    lthing,
                    text(el, "dagur"),
                    start,
                    end,
                    secs,
                    text(el, "tegundræðu"),
                    text(el, "mál/málsheiti"),
                    parse_role(rm),
                )
            )
        con.executemany("INSERT INTO speeches VALUES (?,?,?,?,?,?,?,?,?)", rows)
        print(f"þing {lthing}: {len(rows)} ræður")


def main():
    first = int(sys.argv[1]) if len(sys.argv) > 1 else 148
    last = int(sys.argv[2]) if len(sys.argv) > 2 else 157
    DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB)
    con.executescript(SCHEMA)
    load_sessions(con, first, last)
    load_parties(con)
    member_ids = load_members(con, first, last)
    load_seats(con, member_ids, first, last)
    load_votes(con, first, last)
    load_speeches(con, first, last)
    con.commit()
    for t in ("members", "seats", "votes", "vote_casts", "speeches"):
        print(t, con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0])
    con.close()


if __name__ == "__main__":
    main()
