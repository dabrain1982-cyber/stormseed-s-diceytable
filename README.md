# Stormseed’s Conquest

Ein eigenständig gestaltetes Welt-Eroberungsspiel für DiceyTable.

Der aktuelle Prototyp enthält:

- ein verbindliches Spielmodell mit 42 Ländern, sechs Kontinenten und vollständigen Nachbarschaften,
- drei Brettstile: **Klassisch**, **Taktisch** und **Farbenfroh**,
- für jeden Stil 42 passende Länderkarten,
- für jeden Stil 12 passende Missionskarten,
- eigene Kartenrückseiten sowie ein Cover und ein Vorschaubild für DiceyTable,
- eine vorbereitete physische Startszene mit Brett, beiden Kartenstapeln,
  drei Angriffswürfeln und zwei Verteidigungswürfeln.

Die geografische Grundlage stammt aus den gemeinfreien Daten von [Natural Earth](https://www.naturalearthdata.com/). Brettgrafiken, Kartenaufbau, Symbole und Projektname wurden für dieses Projekt neu erstellt. Es werden keine Markenlogos oder übernommenen Spielgrafiken verwendet.

## Dateien neu erzeugen

Der Generator erwartet eine lokale Natural-Earth-GeoJSON-Datei:

```sh
python3 tools/generate_game_assets.py --geojson /pfad/zu/ne_110m_admin_0_countries.geojson
```

Die einzeln gerenderten Karten unter `assets/decks/*/cards/` bleiben als bearbeitbare Quellen im Repository. DiceyTable lädt im Spiel die erzeugten Kartenbögen unter `assets/textures/decks/`.

Die physische Startszene lässt sich mit einem der drei Stile neu zusammensetzen:

```sh
python3 tools/assemble_scene.py --style klassisch
python3 tools/assemble_scene.py --style taktisch
python3 tools/assemble_scene.py --style farbenfroh
```

Die Würfel verwenden bewusst DiceyTables vorhandenes D6-Modell und dessen integrierte Physik. Für Brett und Karten kommen die nativen Objektarten `board` und `deck` zum Einsatz.
