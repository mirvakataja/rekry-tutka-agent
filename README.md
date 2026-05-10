# rekry-tutka-agent

`rekry-tutka-agent` kerää verkosta talent acquisition -trendeihin ja
rekrytointikeskusteluihin liittyvää sisältöä ja tallentaa löydökset SQLite-
tietokantaan.

Agentti tallentaa jokaisesta artikkelista tai keskustelusta:

- otsikon
- julkaisupäivän, jos se löytyy lähteestä tai sivun metatiedoista
- sisällön tekstimuodossa
- linkin alkuperäiseen sisältöön

Lisäksi LLM-analyysi voi tunnistaa jokaisesta tallennetusta dokumentista enintään
viisi avainsanaa tai lyhyttä aihefraasia kysymykseen "mistä tässä puhutaan?".

## Rakenne

- `config/sources.json` - oletuslähteet RSS/Atom-syötteinä
- `src/rekry_tutka_agent/agent.py` - ajettava keräysagentti
- `src/rekry_tutka_agent/db.py` - SQLite-skeema ja tallennus
- `src/rekry_tutka_agent/llm.py` - LLM-pohjainen avainsana-analyysi
- `src/rekry_tutka_agent/parsers.py` - RSS/Atom-normalisointi
- `src/rekry_tutka_agent/html_extract.py` - linkitettyjen sivujen tekstipoiminta
- `tests/` - yksikkötestit ilman verkkokutsuja

## Käyttö

Luo tietokanta:

```bash
PYTHONPATH=src python3 -m rekry_tutka_agent init-db --database data/rekry_tutka.db
```

Aja keräys oletuslähteillä:

```bash
PYTHONPATH=src python3 -m rekry_tutka_agent run \
  --sources config/sources.json \
  --database data/rekry_tutka.db \
  --limit 20
```

Jos haluat tallentaa vain syötteissä olevan sisällön ilman alkuperäisten
linkkien hakemista:

```bash
PYTHONPATH=src python3 -m rekry_tutka_agent run --no-fetch-linked-content
```

Komento tulostaa JSON-yhteenvedon ajosta, esimerkiksi montako dokumenttia
lisättiin, päivitettiin tai jätettiin ennalleen.

### Päivittäinen keruu

Pitkään käynnissä oleva ajastin ajaa keruun oletuksena kerran vuorokaudessa ja
viikoittaisen avainsana-analyysin kerran seitsemässä päivässä:

```bash
export OPENAI_API_KEY="..."

PYTHONPATH=src python3 -m rekry_tutka_agent schedule \
  --sources config/sources.json \
  --database data/rekry_tutka.db
```

Ajastin tarkistaa oletuksena tunnin välein, onko tehtäviä erääntynyt. Se tallentaa
viimeisimmät onnistuneet ajot tietokannan `scheduled_tasks`-tauluun. Jos haluat
ajaa vain erääntyneet tehtävät kerran esimerkiksi ulkoisesta cronista:

```bash
PYTHONPATH=src python3 -m rekry_tutka_agent schedule --once
```

## Avainsanojen LLM-analyysi

Kun dokumentteja on tallennettu tietokantaan, voit pyytää LLM:ää etsimään
jokaiselle dokumentille enintään viisi avainsanaa:

```bash
export OPENAI_API_KEY="..."

PYTHONPATH=src python3 -m rekry_tutka_agent analyze-keywords \
  --database data/rekry_tutka.db \
  --limit 50
```

Komento analysoi oletuksena vain dokumentit, joilta avainsanat puuttuvat tai
joiden sisältö on muuttunut edellisen analyysin jälkeen. Uudelleenanalysointi
kaikille dokumenteille onnistuu `--force`-valinnalla.

Hyödyllisiä valintoja:

- `--max-keywords 5` - avainsanojen enimmäismäärä, sallittu väli 1-5
- `--output-language Finnish` - LLM:n toivottu vastauskieli
- `--model MODEL` - käytettävä OpenAI-yhteensopiva malli
- `--base-url URL` - vaihtoehtoinen OpenAI-yhteensopiva API-osoite
- `--api-key-env ENV` - ympäristömuuttuja, josta API-avain luetaan

## Viikoittainen avainsanaraportti

Viikkoraportti laskee tallennetuista avainsanoista, kuinka monessa viikon aikana
löydetyssä dokumentissa kukin avainsana esiintyy. Komento tulostaa Markdown-
taulukon, jossa on top10 avainsanaa ja linkit kolmeen esimerkkiesiintymään:

```bash
PYTHONPATH=src python3 -m rekry_tutka_agent weekly-keyword-report \
  --database data/rekry_tutka.db
```

Raportin asetuksia voi säätää:

- `--days 7` - tarkasteluikkuna päivinä
- `--top 10` - tulostettavien avainsanojen määrä
- `--links 3` - esimerkkilinkkien määrä per avainsana
- `--format html` - tulostaa HTML-taulukon sähköpostikäyttöön

## GitHub Actions -sähköpostiraportti

Repo sisältää workflow'n `.github/workflows/weekly-keyword-report.yml`, joka:

- ajaa artikkelien ja keskustelujen keruun päivittäin
- säilyttää SQLite-tietokannan GitHub Actions -cachella ajojen välillä
- ajaa sunnuntaisin LLM-avainsana-analyysin uusille tai muuttuneille dokumenteille
- muodostaa viikoittaisen top10-avainsanataulukon HTML-muodossa
- lähettää taulukon sähköpostiin `mirva.kataja@me.com`
- näyttää esimerkkiesiintymät klikattavina otsikko/lähde-linkkeinä ilman näkyviä
  tekstimuotoisia URL:eja

Workflow'n voi käynnistää myös käsin GitHubin Actions-näkymästä.

Lisää repositoryyn seuraavat GitHub Secrets -arvot:

- `OPENAI_API_KEY` - LLM-avain avainsana-analyysiä varten
- `SMTP_SERVER` - SMTP-palvelin, esimerkiksi `smtp.example.com`
- `SMTP_PORT` - SMTP-portti, esimerkiksi `465` tai `587`
- `SMTP_USERNAME` - SMTP-käyttäjätunnus
- `SMTP_PASSWORD` - SMTP-salasana tai sovelluskohtainen salasana
- `SMTP_FROM` - vapaaehtoinen lähettäjäosoite; jos puuttuu, käytetään `SMTP_USERNAME`

Valinnaiset GitHub Variables -arvot:

- `REKRY_TUTKA_LLM_MODEL` - oletuksena `gpt-4o-mini`
- `OPENAI_BASE_URL` - oletuksena `https://api.openai.com/v1`

## Tietokanta

Agentti luo automaattisesti neljä taulua:

- `documents` - kerätyt artikkelit ja keskustelut
- `ingestion_runs` - ajokertojen tilastot ja virheiden määrä
- `document_keyword_analysis` - LLM:n tuottamat avainsanat dokumenteille
- `scheduled_tasks` - päivittäisen keruun ja viikkoraportin ajotila

`documents.source_url` on uniikki, joten samaa alkuperäistä sisältöä ei tallenneta
useaan kertaan. Jos otsikko, päivämäärä tai sisältö muuttuu, rivi päivitetään.

## Lähteiden lisääminen

Oletuskonfiguraatio sisältää jo Ylen työelämä- ja työnvälityssyötteet sekä
Duunitorin Työelämä-sivuston yleisen ja rekrytointiaiheisen syötteen. Redditin
puolelta mukana ovat `r/recruiting`, `r/Recruitment`,
`r/RecruitmentAnalytics` ja `r/TalentAcquisition`.

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
PYTHONPATH=src python3 -m unittest discover -s tests
```
