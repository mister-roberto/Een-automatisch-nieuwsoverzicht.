# Een automatisch nieuwsoverzicht

Een script dat via GitHub Actions elke dag de feeds van onder meer Rijksoverheid
en Rechtspraak ophaalt en er per week een overzicht in Markdown van schrijft.

**Overzichten lezen:** zie de map [`overzichten`](overzichten/README.md).

## Hoe het werkt

| Onderdeel | Wat het doet |
| --- | --- |
| [`feeds.toml`](feeds.toml) | De lijst met bronnen. Hier voeg je feeds toe of filter je op trefwoorden. |
| [`nieuwsoverzicht.py`](nieuwsoverzicht.py) | Haalt de feeds op en schrijft de overzichten. Alleen de standaardbibliotheek van Python. |
| [`.github/workflows/nieuwsoverzicht.yml`](.github/workflows/nieuwsoverzicht.yml) | Draait het script elke dag om 05:17 UTC en legt het resultaat vast in de repository. |
| `data/berichten.json` | Geheugen van het script: de berichten van de afgelopen vier weken. |
| `overzichten/JJJJ-Www.md` | Eén bestand per week (maandag t/m zondag), per bron gegroepeerd. |

Het script draait dagelijks en niet wekelijks, omdat sommige feeds maar een paar
dagen terugkijken. Het overzicht van de lopende week groeit dus elke dag; na
zondag is het compleet.

## Een bron toevoegen

Zet een blok in `feeds.toml`:

```toml
[[bron]]
naam = "Belastingdienst"
url = "https://voorbeeld.nl/nieuws.rss"
bevat = ["btw", "loonheffing"]   # optioneel: alleen deze onderwerpen
```

RSS 2.0, Atom en Google News-sitemaps worden herkend.

## Zelf draaien

```bash
python nieuwsoverzicht.py
```

Handmatig starten op GitHub kan via **Actions → Nieuwsoverzicht → Run workflow**.

## Goed om te weten

- Geplande workflows draaien alleen vanaf de standaardbranch (`main`).
- GitHub schakelt geplande workflows uit als er 60 dagen niets in de repository
  gebeurt. De dagelijkse commits van het script voorkomen dat.
- Als één bron niet bereikbaar is, verschijnt er een waarschuwing in de run en
  gaat de rest gewoon door.
