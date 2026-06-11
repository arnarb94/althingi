# Alþingisgögn

Óopinber vefur byggður á [opnum gögnum Alþingis](https://www.althingi.is/altext/xml/):
þingmenn, þingflokkar, atkvæðagreiðslur, ræðutími og mæting frá 148. löggjafarþingi (2017) til dagsins í dag.

## Uppbygging

- `etl/` – Python-skriftur sem sækja XML-gögn og vinna úr þeim
  - `scrape.py` – sækir XML af althingi.is í `etl/cache/` (skyndiminni, sækir aðeins nýtt)
  - `build_db.py` – byggir SQLite-grunn (`data/althingi.db`) úr skyndiminninu
  - `export_json.py` – reiknar tölfræði og skrifar JSON fyrir vefinn
- `site/` – Astro-vefur (static site)
  - `site/src/data/` – tölfræði-JSON (þingmenn, flokkar, þing)
  - `site/public/data/` – atkvæðagreiðslulistar hvers þings
- `data/` – SQLite-grunnur (ekki í git)

## Keyrsla

```bash
# 1. Sækja gögn (tekur dágóða stund í fyrsta sinn)
python3 etl/scrape.py 148 157

# 2. Byggja gagnagrunn
python3 etl/build_db.py 148 157

# 3. Skrifa JSON fyrir vefinn
python3 etl/export_json.py

# 4. Byggja/keyra vefinn
cd site
npm install
npm run dev      # þróun
npm run build    # static build í site/dist/
```

Gögnin á althingi.is uppfærast einu sinni á sólarhring; ETL-keyrslan er
hugmynduð (idempotent) og sækir aðeins það sem vantar, svo hana má keyra
daglega (t.d. í GitHub Action) og endurbyggja vefinn.

## Skilgreiningar

- **Mæting**: hlutfall atkvæðagreiðslna þar sem þingmaður var viðstaddur
  (greiddi já, nei eða sat hjá) af öllum atkvæðagreiðslum sem hann var skráður í.
- **Með flokki**: hlutfall já/nei-atkvæða þingmanns sem féllu með meirihluta
  já/nei-atkvæða eigin þingflokks í sömu atkvæðagreiðslu.
- **Ræðutími**: samanlögð lengd ræða (ræðulauk − ræðahófst) úr ræðulista Alþingis.
