# Technik-Reparatur für Off-Grid Szenarien
## Quelle: THW Ausbildung, BSI, VDE

---

### Solarpanel-Diagnose und Reparatur

#### Problem: Panel liefert keinen Strom
1. **Sicherheit:** Panels unter Last NICHT berühren (bis 48V DC!)
2. **Steckverbindungen (MC4):** Prüfen ob fest und korrosionsfrei
   - MC4 trennen → Kontakte mit Schleifpapier (P240) reinigen
   - Feutcht? Trocknen lassen → Kontaktspray (WD40)
3. **Oberfläche:** Verschmutzt? → Mit Wasser + weichem Tuch reinigen
   - KEIN Scheuermittel (zerkratzt Anti-Reflex-Beschichtung)
4. **Schatten-Test:** Auch kleine Teilschatten reduzieren Leistung drastisch
   - Bypass-Dioden in Junction-Box prüfen
5. **Multimeter-Test:**
   - Offene Spannung (Voc): Sollte 80-90% des Datenblatts
   - Kurzschlussstrom (Isc): bei Sonne ca. 1/3 weniger als Datenblatt = defekt

#### Problem: Laderegler zeigt keine Spannung
- Sicherung prüfen (oft im Gehäuse)
- Batterie-Spannung messen (>10.5V für 12V-System)
- Polarität prüfen (Rot=+, Schwarz=-)
- Erdung prüfen bei Metallgehäuse

### Batterie-Management

#### Blei-Säure (AGM/Gel)
- **Vollladung:** 14.4V (12V-System)
- **Tiefentladeschutz:** Nie unter 10.5V (50% SOC)
  - Unter 10.5V = permanenter Kapazitätsverlust!
- **Temperatur:** Kapazität sinkt bei Kälte (~1%/°C unter 25°C)
- **Wartung:** AGM/Gel: wartungsfrei. Flüssig: Destilliertes Wasser nachfüllen

#### Lithium (LiFePO4)
- **Vollladung:** 14.6V (12V-System)
- **Tiefentladeschutz:** BMS (Battery Management System) integriert
- **Kälte-Limit:** NICHT laden unter 0°C! (Lithium-Plating = Kurzschluss!)
- **Heizen:** Bei Kälte: Batterie erst in warme Umgebung (Auto, Zelt)
- **Zyklen:** 2000-5000 Zyklen → deutlich langlebiger als Blei

#### DIY-Powerbank aus 18650-Zellen
- **Spannung:** 1 Zelle = 3.7V nominal, 4.2V voll
- **Kapazität:** Typisch 2600-3500mAh pro Zelle
- **USB-Bank:** 1S-Konfiguration + Step-Up auf 5V
- **SICHERHEIT:** Nur geschützte Zellen! Ohne PCB → Explosionsgefahr
- **Parallelschaltung:** Nur gleichwertige Zellen (Hersteller, Kapazität, Alter)

### Funk und Kommunikation

#### PMR446 (ohne Lizenz, jeder darf)
- **Frequenz:** 446.0-446.2 MHz, 8+8 Kanäle
- **Leistung:** Max. 0.5W ERP (in DE)
- **Reichweite:** 1-5km (Gelände), bis 10km (freie Sicht)
- **Tipp:** Kanal 1-8 (analog), 9-16 (digital/CTCSS)
- **Batterie:** AA-Akkus, ca. 20h Standby

#### CB-Funk (ohne Lizenz)
- **Frequenz:** 26.965-27.405 MHz, 80 Kanäle (in DE)
- **Leistung:** 4W AM, 12W SSB
- **Reichweite:** 5-30km (Gelände), >100km (Atmosphäre/"Skip")
- **Notkanal:** Kanal 9 (international)
- **Antenne:** Länge wichtig! Lambda/4 = 2.75m (Autoantenne)

#### Notsignale
- **SOS:** · · · — — — · · · (Morsezeichen: 3 kurz, 3 lang, 3 kurz)
- **Pfeife:** 6× kurz, 1 Min Pause, wiederholen
- **Spiegel-Signal:** Sonnenlicht reflektieren, fächerförmig schwenken
- **Feuer:** 3 Feuer im Dreieck = internationales Notsignal
- **Boden-Signale (Flugrettung):**
  - V = Hilfe benötigt
  - X = Medizinische Hilfe
  - → = Folge dieser Richtung
  - LL = Alles OK

### Wasserfilter-Systeme

#### Sawyer Squeeze / Mini
- **Porengröße:** 0.1 Mikron (Absolute)
- **Entfernt:** Bakterien (99.99999%), Protozoen (99.9999%)
- **Entfernt NICHT:** Viren, Chemikalien
- **Durchfluss:** ~1.8L/Min (Squeeze), ~0.5L/Min (Mini)
- **Reinigung:** Rückspülen mit sauberer Spritze
- **Lebensdauer:** Bis zu 400.000 Liter (mit Rückspülung)
- **Frostschutz:** NICHT einfrieren lassen! (Hohlfasern brechen)

#### LifeStraw
- **Porengröße:** 0.2 Mikron
- **Entfernt:** Bakterien, Parasiten
- **Kapazität:** ~4000 Liter
- **Trinken direkt** aus der Quelle oder Kanal: Filterteil eintauchen
- **Nachteil:** Kann kein Wasser für die Gruppe filtern

#### Improvisierten Filter bauen
```
┌─────────────────┐
│  Auffanggefäß    │  ← Sauberes Wasser
├─────────────────┤
│  Sand (fein)     │  10cm
├─────────────────┤
│  Kies (mittel)   │  5cm
├─────────────────┤
│  Aktivkohle      │  10cm  ← aus Lagerfeuer (Holzkohle zerkleinern)
├─────────────────┤
│  Kies (grob)     │  5cm
├─────────────────┤
│  Sand (fein)     │  10cm
├─────────────────┤
│  Stoff/Gaze      │  ← Vorfilter (grobe Partikel)
└─────────────────┘
WICHTIG: Nach dem Filtern ABKOCHEN! (3 Minuten)
Filter entfernt Trübstoffe aber nicht alle Keime.
```

### Generator-Betrieb

#### Benzin-Generator (Inverter)
- **LEBENSGEFAHR:** Kohlenmonoxid (CO) ist geruchlos und tödlich!
  - NUR im Freien betreiben (min. 5m von Gebäuden)
  - In Garage NICHT betreiben, auch nicht mit offener Tür!
- **Erdung:** Erdungsspeer oder Wasserleitung
- **Betankung:** Motor AUS, 5 Min abkühlen lassen
- **Lastmanagement:** Nicht über 80% Nennleistung dauerhaft

#### Benzin lagern
- Max. 20L in zugelassenen Kanistern (Blech oder PE)
- Kühl, trocken, belüftet, NICHT im Wohngebäude
- Haltbarkeit: 6-12 Monate (mit Stabilisator: bis 24 Monate)
- Benzin-Stabilisator: 30ml pro 10L
