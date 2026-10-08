# Allie UCI für NixOS

Vier Dateien: `install.sh`, `start.sh`, `engine.py`, `shell.nix`.

```sh
chmod +x install.sh start.sh
./install.sh
./start.sh
```

In En Croissant als lokale Engine auswählen:
`/home/shadespice/.local/share/allie-uci-0aace9ab/start.sh`.

Der Installer lädt Allie 2.0 und baut die Rust-Suche. Er aktualisiert auch eine
vorhandene Installation; heruntergeladene Modellgewichte werden wiederverwendet.
Ein eigener Installationsordner muss als absoluter Pfad übergeben werden.

Elo und Grundbedenkzeit über die UCI-Optionen `UCI_Elo` und `BaseTime` setzen.
Standard-UCI liefert aktuelle Restzeiten und Inkremente, aber keine vollständige
historische Uhrzeitfolge oder eindeutig die anfängliche Grundbedenkzeit.
Vollständige Zugfolgen ab der Anfangsstellung sind erforderlich.

Parser- und Modelltests sind in `engine.py` integriert und laufen bei der
Installation. Fehler mit Traceback stehen in
`test-results/stderr.log` im Installationsordner.

Rust Calibrated Mode ist verpflichtend. `stop` greift zwischen Inferenzbatches.
Beliebige FEN-Stellungen sowie `depth`, `mate` und `searchmoves` sind derzeit
nicht unterstützt. Eine vollständige Partie und En Croissant unter NixOS sind
hier noch nicht bestätigt.
