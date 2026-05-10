# rekry-tutka-agent

`rekry-tutka-agent` kerää verkosta talent acquisition -trendeihin ja
rekrytointikeskusteluihin liittyvää sisältöä ja tallentaa löydökset SQLite-
tietokantaan.

Agentti tallentaa jokaisesta artikkelista tai keskustelusta:

- otsikon
- julkaisupäivän, jos se löytyy lähteestä tai sivun metatiedoista
- sisällön tekstimuodossa
- linkin alkuperäiseen sisältöön

## Rakenne

- `config/sources.json` - oletuslähteet RSS/Atom-syötteinä
- `src/rekry_tutka_agent/agent.py` - ajettava keräysagentti
- `src/rekry_tutka_agent/db.py` - SQLite-skeema ja tallennus
- `src/rekry_tutka_agent/parsers.py` - RSS/Atom-normalisointi
- `src/rekry_tutka_agent/html_extract.py` - linkitettyjen sivujen tekstipoiminta
- `tests/` - yksikkötestit ilman verkkokutsuja

## Käyttö

Luo tietokanta:

```bash
PYTHONPATH=src python -m rekry_tutka_agent init-db --database data/rekry_tutka.db
```

Aja keräys oletuslähteillä:

```bash
PYTHONPATH=src python -m rekry_tutka_agent run \
  --sources config/sources.json \
  --database data/rekry_tutka.db \
  --limit 20
```

Jos haluat tallentaa vain syötteissä olevan sisällön ilman alkuperäisten
linkkien hakemista:

```bash
PYTHONPATH=src python -m rekry_tutka_agent run --no-fetch-linked-content
```

Komento tulostaa JSON-yhteenvedon ajosta, esimerkiksi montako dokumenttia
lisättiin, päivitettiin tai jätettiin ennalleen.

## Tietokanta

Agentti luo automaattisesti kaksi taulua:

- `documents` - kerätyt artikkelit ja keskustelut
- `ingestion_runs` - ajokertojen tilastot ja virheiden määrä

`documents.source_url` on uniikki, joten samaa alkuperäistä sisältöä ei tallenneta
useaan kertaan. Jos otsikko, päivämäärä tai sisältö muuttuu, rivi päivitetään.

## Lähteiden lisääminen

Lisää uusi RSS- tai Atom-lähde `config/sources.json`-tiedostoon:

```json
{
  "name": "Example source",
  "type": "feed",
  "url": "https://example.com/feed.xml",
  "tags": ["news", "talent-acquisition"],
  "fetch_content": true
}
```

`fetch_content: true` hakee syötteessä olevan linkin ja yrittää poimia sivulta
luettavan tekstisisällön. `false` käyttää vain syötteen mukana tulevaa sisältöä,
mikä sopii usein keskustelu- ja hakusyötteisiin.

## Testit

```bash
PYTHONPATH=src python -m unittest discover -s tests
```
