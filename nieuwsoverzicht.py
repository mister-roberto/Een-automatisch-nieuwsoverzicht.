#!/usr/bin/env python3
"""Haalt feeds op en schrijft per week een nieuwsoverzicht in Markdown.

Het script is bedoeld om dagelijks te draaien. Elke keer:

1. haalt het de bronnen uit feeds.toml op;
2. voegt het nieuwe berichten toe aan data/berichten.json;
3. schrijft het de overzichten van de lopende en de vorige week opnieuw
   naar overzichten/JJJJ-Www.md.

Alleen de standaardbibliotheek is nodig (Python 3.11 of nieuwer).
"""

from __future__ import annotations

import html
import json
import re
import sys
import tomllib
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

MAP = Path(__file__).resolve().parent
CONFIG = MAP / "feeds.toml"
OPSLAG = MAP / "data" / "berichten.json"
UITVOER = MAP / "overzichten"

TIJDZONE = ZoneInfo("Europe/Amsterdam")
BEWAARDAGEN = 28  # ruim genoeg om de vorige week volledig te kunnen herschrijven
SAMENVATTING_MAX = 280

DAGEN = ["ma", "di", "wo", "do", "vr", "za", "zo"]
MAANDEN = ["januari", "februari", "maart", "april", "mei", "juni", "juli",
           "augustus", "september", "oktober", "november", "december"]


# ---------------------------------------------------------------- ophalen

def haal_op(url: str) -> bytes:
    verzoek = urllib.request.Request(url, headers={
        "User-Agent": "nieuwsoverzicht/1.0 (feedlezer)",
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
    })
    with urllib.request.urlopen(verzoek, timeout=30) as antwoord:
        return antwoord.read()


def kaal(tag: str) -> str:
    """Elementnaam zonder XML-namespace."""
    return tag.rsplit("}", 1)[-1]


def tekst(element: ET.Element, *namen: str) -> str:
    """Tekst van het eerste (klein)kind met een van de gegeven namen."""
    for naam in namen:
        for kind in element.iter():
            if kind is not element and kaal(kind.tag) == naam and kind.text and kind.text.strip():
                return kind.text.strip()
    return ""


def opschonen(waarde: str) -> str:
    """HTML weghalen en witruimte samenvoegen."""
    waarde = re.sub(r"<[^>]+>", " ", waarde)
    waarde = html.unescape(waarde)
    return re.sub(r"\s+", " ", waarde).strip()


def lees_datum(waarde: str) -> datetime | None:
    if not waarde:
        return None
    try:
        datum = datetime.fromisoformat(waarde)
    except ValueError:
        try:
            datum = parsedate_to_datetime(waarde)
        except (TypeError, ValueError):
            return None
    if datum.tzinfo is None:
        datum = datum.replace(tzinfo=TIJDZONE)
    return datum


def lees_feed(inhoud: bytes) -> list[dict]:
    """Leest RSS 2.0, Atom of een (nieuws-)sitemap en geeft berichten terug."""
    wortel = ET.fromstring(inhoud.lstrip(b"\xef\xbb\xbf \r\n\t"))
    berichten = []
    for element in wortel.iter():
        soort = kaal(element.tag)
        if soort == "item":  # RSS
            link = tekst(element, "link") or tekst(element, "guid")
            datum = tekst(element, "pubDate", "date")
            samenvatting = tekst(element, "description")
        elif soort == "entry":  # Atom
            link = ""
            for kind in element:
                if kaal(kind.tag) == "link" and kind.get("href"):
                    if kind.get("rel", "alternate") == "alternate" or not link:
                        link = kind.get("href")
            datum = tekst(element, "published", "updated")
            samenvatting = tekst(element, "summary", "content")
        elif soort == "url":  # sitemap
            link = tekst(element, "loc")
            datum = tekst(element, "publication_date", "lastmod")
            samenvatting = ""
        else:
            continue
        titel = opschonen(tekst(element, "title"))
        if not link or not titel:
            continue
        berichten.append({
            "link": link.strip(),
            "titel": titel,
            "samenvatting": opschonen(samenvatting),
            "datum": lees_datum(datum),
        })
    return berichten


def past(bericht: dict, bron: dict) -> bool:
    titel = bericht["titel"].lower()
    if any(woord.lower() in titel for woord in bron.get("zonder", [])):
        return False
    bevat = bron.get("bevat")
    if bevat:
        alles = titel + " " + bericht["samenvatting"].lower()
        return any(woord.lower() in alles for woord in bevat)
    return True


# ---------------------------------------------------------------- schrijven

def weeknaam(datum: datetime) -> str:
    jaar, week, _ = datum.astimezone(TIJDZONE).isocalendar()
    return f"{jaar}-W{week:02d}"


def weekbereik(naam: str) -> tuple[datetime, datetime]:
    jaar, week = naam.split("-W")
    maandag = datetime.fromisocalendar(int(jaar), int(week), 1)
    return maandag, maandag + timedelta(days=6)


def lang(datum: datetime) -> str:
    return f"{datum.day} {MAANDEN[datum.month - 1]} {datum.year}"


def inkorten(waarde: str) -> str:
    if len(waarde) <= SAMENVATTING_MAX:
        return waarde
    return waarde[:SAMENVATTING_MAX].rsplit(" ", 1)[0].rstrip(".,;:") + "…"


def markdown(waarde: str) -> str:
    """Tekens onschadelijk maken die Markdown anders als opmaak leest."""
    return re.sub(r"([\\\[\]*_`<>|])", r"\\\1", waarde)


def schrijf_week(naam: str, berichten: list[dict], bronnen: list[str], nu: datetime) -> Path:
    maandag, zondag = weekbereik(naam)
    week = int(naam.split("-W")[1])
    regels = [
        f"# Nieuwsoverzicht week {week} ({lang(maandag)} t/m {lang(zondag)})",
        "",
        f"_{len(berichten)} berichten · bijgewerkt op {lang(nu)} om {nu:%H:%M} uur_",
        "",
    ]
    # Bronnen in de volgorde van feeds.toml; verwijderde bronnen achteraan.
    volgorde = bronnen + sorted({b["bron"] for b in berichten} - set(bronnen))
    for bron in volgorde:
        van_bron = [b for b in berichten if b["bron"] == bron]
        if not van_bron:
            continue
        van_bron.sort(key=lambda b: b["datum"], reverse=True)
        regels += [f"## {bron} ({len(van_bron)})", ""]
        for b in van_bron:
            datum = datetime.fromisoformat(b["datum"]).astimezone(TIJDZONE)
            dag = f"{DAGEN[datum.weekday()]} {datum.day} {MAANDEN[datum.month - 1][:3]}"
            link = b["link"].replace("(", "%28").replace(")", "%29").replace(" ", "%20")
            regels.append(f"- **{dag}** — [{markdown(b['titel'])}]({link})")
            if b.get("samenvatting"):
                regels.append(f"  <br>{markdown(inkorten(b['samenvatting']))}")
        regels.append("")
    UITVOER.mkdir(exist_ok=True)
    pad = UITVOER / f"{naam}.md"
    pad.write_text("\n".join(regels), encoding="utf-8")
    return pad


def schrijf_index() -> None:
    regels = ["# Weekoverzichten", ""]
    for pad in sorted(UITVOER.glob("????-W??.md"), reverse=True):
        maandag, zondag = weekbereik(pad.stem)
        week = int(pad.stem.split("-W")[1])
        regels.append(f"- [Week {week}, {maandag.year}]({pad.name}) — {lang(maandag)} t/m {lang(zondag)}")
    regels.append("")
    (UITVOER / "README.md").write_text("\n".join(regels), encoding="utf-8")


# ---------------------------------------------------------------- hoofdprogramma

def main() -> int:
    nu = datetime.now(TIJDZONE)
    bronnen = tomllib.loads(CONFIG.read_text(encoding="utf-8")).get("bron", [])
    if not bronnen:
        print("Geen bronnen in feeds.toml.", file=sys.stderr)
        return 1

    opslag: dict[str, dict] = {}
    if OPSLAG.exists():
        opslag = json.loads(OPSLAG.read_text(encoding="utf-8"))

    gelukt = 0
    for bron in bronnen:
        try:
            berichten = lees_feed(haal_op(bron["url"]))
        except Exception as fout:  # één kapotte bron mag de rest niet tegenhouden
            print(f"::warning::{bron['naam']}: ophalen mislukt ({fout})")
            continue
        gelukt += 1
        berichten = [b for b in berichten if past(b, bron)]
        if "maximum" in bron:
            berichten = berichten[: bron["maximum"]]
        nieuw = 0
        for b in berichten:
            if b["link"] in opslag:
                continue
            opslag[b["link"]] = {
                "bron": bron["naam"],
                "titel": b["titel"],
                "samenvatting": b["samenvatting"],
                # Zonder datum in de feed telt het moment waarop we het bericht zagen.
                "datum": (b["datum"] or nu).astimezone(timezone.utc).isoformat(timespec="seconds"),
            }
            nieuw += 1
        print(f"{bron['naam']}: {len(berichten)} berichten, waarvan {nieuw} nieuw")

    if not gelukt:
        print("Geen enkele bron kon worden opgehaald.", file=sys.stderr)
        return 1

    grens = (nu - timedelta(days=BEWAARDAGEN)).astimezone(timezone.utc).isoformat()
    opslag = {link: b for link, b in opslag.items() if b["datum"] >= grens}

    OPSLAG.parent.mkdir(exist_ok=True)
    OPSLAG.write_text(
        json.dumps(dict(sorted(opslag.items())), ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )

    namen = [b["naam"] for b in bronnen]
    for week in {weeknaam(nu), weeknaam(nu - timedelta(days=7))}:
        van_week = [
            {"link": link, **b} for link, b in opslag.items()
            if weeknaam(datetime.fromisoformat(b["datum"])) == week
        ]
        if van_week:
            pad = schrijf_week(week, van_week, namen, nu)
            print(f"Geschreven: {pad.relative_to(MAP)} ({len(van_week)} berichten)")
    schrijf_index()
    return 0


if __name__ == "__main__":
    sys.exit(main())
