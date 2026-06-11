"""Sækir XML-gögn af althingi.is og vistar í skyndiminni (etl/cache/).

Notkun: python etl/scrape.py [fyrsta_thing] [sidasta_thing]
"""
import concurrent.futures as cf
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

BASE = "https://www.althingi.is/altext/xml"
CACHE = Path(__file__).parent / "cache"
HEADERS = {"User-Agent": "althingi-opin-gogn (opinber gogn, hofleg notkun)"}


def fetch(url: str, dest: Path, force: bool = False) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0 and not force:
        return dest
    for attempt in range(8):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=120) as r:
                data = r.read()
            dest.write_bytes(data)
            time.sleep(0.05)
            return dest
        except urllib.error.HTTPError as e:
            if e.code == 429:
                if attempt == 7:
                    raise
                time.sleep(15 + 10 * attempt)
            elif attempt == 7:
                raise
            else:
                time.sleep(2 * (attempt + 1))
        except Exception as e:
            if attempt == 7:
                raise
            time.sleep(2 * (attempt + 1))
            print(f"  endurreyni {url}: {e}", file=sys.stderr)
    return dest


def fetch_session(lthing: int) -> None:
    d = CACHE / str(lthing)
    print(f"þing {lthing}: grunnskrár")
    fetch(f"{BASE}/thingmenn/?lthing={lthing}", d / "thingmenn.xml")
    fetch(f"{BASE}/raedulisti/?lthing={lthing}", d / "raedulisti.xml")
    fetch(f"{BASE}/atkvaedagreidslur/?lthing={lthing}", d / "atkvaedagreidslur.xml")

    # einstakar atkvæðagreiðslur
    root = ET.parse(d / "atkvaedagreidslur.xml").getroot()
    nums = [el.get("atkvæðagreiðslunúmer") for el in root.iter("atkvæðagreiðsla")]
    nums = [n for n in nums if n]
    todo = [n for n in nums if not (d / "atkv" / f"{n}.xml").exists()]
    print(f"þing {lthing}: {len(nums)} atkvæðagreiðslur ({len(todo)} ósóttar)")
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        futs = [
            ex.submit(
                fetch,
                f"{BASE}/atkvaedagreidslur/atkvaedagreidsla/?numer={n}",
                d / "atkv" / f"{n}.xml",
            )
            for n in todo
        ]
        for i, f in enumerate(cf.as_completed(futs)):
            f.result()
            if (i + 1) % 200 == 0:
                print(f"þing {lthing}: {i + 1}/{len(todo)}")


def fetch_members(lthing_range) -> None:
    ids = set()
    for lthing in lthing_range:
        f = CACHE / str(lthing) / "thingmenn.xml"
        if not f.exists():
            continue
        root = ET.parse(f).getroot()
        ids.update(el.get("id") for el in root.iter("þingmaður"))
    ids.discard(None)
    print(f"{len(ids)} þingmenn: sæki þingsetu")
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        futs = [
            ex.submit(
                fetch,
                f"{BASE}/thingmenn/thingmadur/thingseta/?nr={i}",
                CACHE / "thingmenn" / f"thingseta_{i}.xml",
            )
            for i in sorted(ids)
        ]
        for f in cf.as_completed(futs):
            f.result()


def main() -> None:
    first = int(sys.argv[1]) if len(sys.argv) > 1 else 148
    last = int(sys.argv[2]) if len(sys.argv) > 2 else 157
    fetch(f"{BASE}/loggjafarthing/", CACHE / "loggjafarthing.xml", force=True)
    fetch(f"{BASE}/thingflokkar/", CACHE / "thingflokkar.xml", force=True)
    rng = range(first, last + 1)
    for lthing in rng:
        fetch_session(lthing)
    fetch_members(rng)
    print("lokið")


if __name__ == "__main__":
    main()
