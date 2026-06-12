"""Reiknar tölfræði úr data/althingi.db og skrifar JSON fyrir vefinn.

Skrifar:
  site/src/data/sessions.json
  site/src/data/parties.json
  site/src/data/members.json
  site/public/data/votes_{lthing}.json   (atkvæðagreiðslulisti hvers þings)
  site/public/data/vote/{num}.json       (einstök atkvæðagreiðsla með atkvæðaskrá)
"""
import json
import sqlite3
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent.parent
DB = ROOT / "data" / "althingi.db"
SRC_DATA = ROOT / "site" / "src" / "data"
PUB_DATA = ROOT / "site" / "public" / "data"

PRESENT = {"já", "nei", "greiðir ekki atkvæði"}


def dump(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))


def main() -> None:
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    sessions = [dict(r) for r in con.execute("SELECT * FROM sessions ORDER BY num")]
    dump(SRC_DATA / "sessions.json", sessions)

    members = {r["id"]: dict(r) for r in con.execute("SELECT * FROM members")}

    # þingsæti við lok þings: aðalmenn sem sátu á viðmiðunardegi (síðasti skráði
    # útgöngudagur þingsins, eða í dag fyrir yfirstandandi þing) — alltaf 63 sæti
    def pdate(s):
        d, m, y = s.split(".")
        return date(int(y), int(m), int(d))

    main_seats = defaultdict(list)  # lthing -> [(member_id, party_id, date_in, date_out)]
    for r in con.execute("SELECT lthing, member_id, party_id, date_in, date_out FROM seats WHERE type != 'varamaður'"):
        main_seats[r["lthing"]].append(
            (r["member_id"], r["party_id"],
             pdate(r["date_in"]) if r["date_in"] else None,
             pdate(r["date_out"]) if r["date_out"] else None)
        )
    party_seats = defaultdict(lambda: defaultdict(int))  # lthing -> party_id -> sæti
    for lt, rows_ in main_seats.items():
        ref = max((o for _, _, _, o in rows_ if o), default=None) or date.today()
        holders = {}
        for mid, pid, i, o in rows_:
            if i and i <= ref and (o is None or o >= ref):
                holders[mid] = pid
        for pid in holders.values():
            party_seats[lt][pid] += 1

    # þingseta: flokkur/kjördæmi hvers þingmanns á hverju þingi
    seat = {}  # (mid, lthing) -> seatrow
    for r in con.execute("SELECT * FROM seats ORDER BY date_in"):
        key = (r["member_id"], r["lthing"])
        prev = seat.get(key)
        # aðalmaður gengur fyrir varamanni í yfirliti
        if prev is None or (prev["type"] == "varamaður" and r["type"] != "varamaður"):
            seat[key] = dict(r)

    # ræðutölfræði
    speech_stats = defaultdict(lambda: {"speeches": 0, "seconds": 0})
    for r in con.execute(
        "SELECT member_id, lthing, COUNT(*) c, COALESCE(SUM(seconds),0) s"
        " FROM speeches GROUP BY member_id, lthing"
    ):
        speech_stats[(r["member_id"], r["lthing"])] = {"speeches": r["c"], "seconds": r["s"]}

    # atkvæði
    votes = {r["num"]: dict(r) for r in con.execute("SELECT * FROM votes")}
    casts_by_vote = defaultdict(list)
    for r in con.execute("SELECT vote_num, member_id, vote FROM vote_casts"):
        casts_by_vote[r["vote_num"]].append((r["member_id"], r["vote"]))

    vote_stats = defaultdict(
        lambda: {"ja": 0, "nei": 0, "sat_hja": 0, "bodadi_fjarvist": 0, "fjarverandi": 0,
                 "med_flokki": 0, "flokks_atkvaedi": 0}
    )
    for vnum, casts in casts_by_vote.items():
        lthing = votes[vnum]["lthing"]
        # meirihluti flokks í þessari atkvæðagreiðslu
        party_tally = defaultdict(lambda: defaultdict(int))
        for mid, v in casts:
            s = seat.get((mid, lthing))
            if s and s["party_id"] and v in ("já", "nei"):
                party_tally[s["party_id"]][v] += 1
        party_major = {
            pid: ("já" if t["já"] >= t["nei"] else "nei") if t["já"] != t["nei"] else None
            for pid, t in party_tally.items()
        }
        for mid, v in casts:
            st = vote_stats[(mid, lthing)]
            if v == "já":
                st["ja"] += 1
            elif v == "nei":
                st["nei"] += 1
            elif v == "greiðir ekki atkvæði":
                st["sat_hja"] += 1
            elif v == "boðaði fjarvist":
                st["bodadi_fjarvist"] += 1
            else:
                st["fjarverandi"] += 1
            if v in ("já", "nei"):
                s = seat.get((mid, lthing))
                maj = party_major.get(s["party_id"]) if s and s["party_id"] else None
                if maj:
                    st["flokks_atkvaedi"] += 1
                    if v == maj:
                        st["med_flokki"] += 1

    # members.json
    out_members = []
    for mid, m in members.items():
        per = []
        lthings = sorted({lt for (i, lt) in seat if i == mid})
        for lt in lthings:
            s = seat[(mid, lt)]
            sp = speech_stats[(mid, lt)]
            vs = vote_stats[(mid, lt)]
            total_votes = vs["ja"] + vs["nei"] + vs["sat_hja"] + vs["bodadi_fjarvist"] + vs["fjarverandi"]
            present = vs["ja"] + vs["nei"] + vs["sat_hja"]
            per.append({
                "lthing": lt,
                "flokkur_id": s["party_id"],
                "flokkur": s["party_name"],
                "kjordaemi": s["constituency"],
                "tegund": s["type"],
                **sp,
                **{k: vs[k] for k in ("ja", "nei", "sat_hja", "bodadi_fjarvist", "fjarverandi")},
                "atkvaedi_alls": total_votes,
                "maeting": round(present / total_votes, 4) if total_votes else None,
                "med_flokki": round(vs["med_flokki"] / vs["flokks_atkvaedi"], 4)
                if vs["flokks_atkvaedi"] else None,
            })
        if not per:
            continue
        out_members.append({
            "id": mid,
            "nafn": m["name"],
            "faedingardagur": m["birth"],
            "skammstofun": m["abbr"],
            "thing": per,
        })
    out_members.sort(key=lambda m: m["nafn"])
    dump(SRC_DATA / "members.json", out_members)

    # parties.json
    parties = {r["id"]: dict(r) for r in con.execute("SELECT * FROM parties")}
    party_sessions = defaultdict(lambda: defaultdict(
        lambda: {"members": set(), "speeches": 0, "seconds": 0,
                 "ja": 0, "nei": 0, "sat_hja": 0, "bodadi_fjarvist": 0, "fjarverandi": 0}
    ))
    for m in out_members:
        for p in m["thing"]:
            if not p["flokkur_id"]:
                continue
            agg = party_sessions[p["flokkur_id"]][p["lthing"]]
            agg["members"].add(m["id"])
            agg["speeches"] += p["speeches"]
            agg["seconds"] += p["seconds"]
            for k in ("ja", "nei", "sat_hja", "bodadi_fjarvist", "fjarverandi"):
                agg[k] += p[k]
    out_parties = []
    for pid, per in party_sessions.items():
        p = parties.get(pid, {})
        rows = []
        lthings = set(per) | {lt for lt, by_party in party_seats.items() if by_party.get(pid)}
        for lt in sorted(lthings):
            a = per[lt]
            total = a["ja"] + a["nei"] + a["sat_hja"] + a["bodadi_fjarvist"] + a["fjarverandi"]
            present = a["ja"] + a["nei"] + a["sat_hja"]
            rows.append({
                "lthing": lt, "members": len(a["members"]),
                "seats": party_seats[lt].get(pid, 0),
                "speeches": a["speeches"], "seconds": a["seconds"],
                **{k: a[k] for k in ("ja", "nei", "sat_hja", "bodadi_fjarvist", "fjarverandi")},
                "maeting": round(present / total, 4) if total else None,
            })
        out_parties.append({
            "id": pid,
            "heiti": (p.get("name") or "").strip() or None,
            "skammstofun": p.get("abbr_short"),
            "thing": rows,
        })
    out_parties.sort(key=lambda p: p["heiti"] or "")
    dump(SRC_DATA / "parties.json", out_parties)

    # atkvæðagreiðslulistar með þjappaðri atkvæðaskrá (j/n/g/b/f)
    CODE = {"já": "j", "nei": "n", "greiðir ekki atkvæði": "g",
            "boðaði fjarvist": "b", "fjarverandi": "f"}
    by_session = defaultdict(list)
    for v in votes.values():
        by_session[v["lthing"]].append(v)
    for lt, vs in by_session.items():
        vs.sort(key=lambda v: (v["time"] or "", v["num"]))
        menn = {}
        rows = []
        for v in vs:
            casts = casts_by_vote.get(v["num"], [])
            for mid, _ in casts:
                if mid not in menn:
                    s = seat.get((mid, lt))
                    menn[mid] = {
                        "n": members[mid]["name"] if mid in members else str(mid),
                        "f": (s or {}).get("party_name"),
                    }
            rows.append({
                "num": v["num"], "timi": v["time"], "mal": v["issue_name"],
                "malsnr": v["issue_num"], "tegund": v["type_text"],
                "ja": v["yes"], "nei": v["no"], "sat_hja": v["abstain"],
                "nidurstada": v["result"],
                "atkv": {str(mid): CODE.get(vv, "f") for mid, vv in casts} or None,
            })
        dump(PUB_DATA / f"votes_{lt}.json", {"menn": menn, "atkvaedagreidslur": rows})

    print(f"members: {len(out_members)}, parties: {len(out_parties)}, "
          f"votes: {len(votes)}, vote details: {len(casts_by_vote)}")
    con.close()


if __name__ == "__main__":
    main()
