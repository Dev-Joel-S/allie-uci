# Allie UCI für NixOS

- `install.sh`: installieren oder vorhandene Installation aktualisieren
- `start.sh`: Engine starten
- `engine.py`: UCI-Code mit integrierten Tests
- `shell.nix`: NixOS-Umgebung

```sh
chmod +x install.sh start.sh
./install.sh
./start.sh
```

In En Croissant diese Datei als lokale Engine auswählen:

```text
/home/shadespice/.local/share/allie-uci-0aace9ab/start.sh
```

Standardordner: `$HOME/.local/share/allie-uci-0aace9ab`.
Der Installer verwendet vorhandene Modellgewichte weiter und baut das Rust-Modul
neu. Für einen anderen Ordner dem Installer einen absoluten Pfad übergeben.

Elo über `UCI_Elo`, anfängliche Bedenkzeit in Sekunden über `BaseTime` einstellen.

Die INT8-Umwandlung wird beim ersten Modellstart gespeichert. Weitere Starts laden
den Cache, statt erneut zu quantisieren. Der Cache braucht zusätzlich ungefähr
6,4 GB Speicherplatz und wird bei geänderten Modellgewichten neu erzeugt.

## Uhrenfehler in En Croissant

Für En Croissant 0.15.1 liegt ein gezielter Patch unter
[ideas/en-croissant-clock.patch](ideas/en-croissant-clock.patch).
`GameManager::get_engine_logs` hält bisher den Spielzustand gesperrt, während
es auf die Engine-Sperre wartet. Während einer langen Suche können dadurch
Uhr-Updates blockieren. Der Patch kopiert die Engine-Referenz und gibt die
Spiel-Sperre vor dem Warten frei.

Die GitHub-Actions-Regression verwendet die tatsächlichen Methoden aus dem
En-Croissant-Quellcode: Sie reproduziert die Blockierung vor dem Patch und prüft
die Erreichbarkeit der Uhr danach. Nach einem weißen `Ng3` läuft nur Schwarz;
nach der verzögerten schwarzen Antwort läuft nur Weiß. Allies tatsächlicher
Code zur Auswahl von `wtime`, `btime`, `winc`, `binc` wird ebenfalls geprüft.

Der Patch muss auf En Croissants Quellcode angewendet und die Anwendung neu
gebaut werden. `install.sh` installiert den Allie-Adapter und ändert die separat
installierte GUI nicht. Die konkrete gemeldete Farbvertauschung wurde ohne
Partie-Logs noch nicht reproduziert; dieser Patch behebt den separat belegten
Sperrfehler. Ein vollständiger Test der GUI unter NixOS steht aus.

## Elo in En Croissant einstellen

Unter **Engines → Allie → Erweiterte Einstellungen** das Feld **UCI_Elo**
ändern (800–2600), dann eine neue Partie starten und Allie erneut auswählen.
Die Einstellung wird dort automatisch gespeichert. Das allgemeine Feld
**ELO** unter „Allgemeine Einstellungen“ ist nur eine angezeigte Bewertung;
es steuert die Spielstärke nicht. In der Partieauswahl selbst blendet
En Croissant 0.15.1 die erweiterten UCI-Optionen aus.

## En Croissant aus dem Nix Store mit Patch bauen

Im heruntergeladenen Repository ausführen:

```sh
nix-build ./ideas/en-croissant-patched.nix -o en-croissant-patched
./en-croissant-patched/bin/en-croissant
```

Das lädt automatisch den geprüften Nixpkgs-Stand
`d261affe5e054396f3bf4ec799f304827b7f8b85` und baut dessen En Croissant 0.15.1
mit dem Patch neu. Es verwendet weder deinen Kanal noch `<nixpkgs>` und verändert
keine vorhandenen Store-Dateien. Der erste GUI-Build kann länger dauern. Die gestartete
Anwendung verwendet weiterhin deine vorhandene Allie-Installation.
Dieser Befehl ersetzt noch keinen Eintrag in deiner NixOS-/Home-Manager-Konfiguration.

## Befund aus ideas/logs.txt

Nach dem weißen `e2g3` (Ng3, 19. Halbzug) sendet die GUI
`wtime 1641918 btime 1769767 winc 2000 binc 2000`.
Allie antwortet nach 190305 ms mit `bestmove g7g6`.
Beim nächsten Suchauftrag beträgt `btime` 1581461 ms:
188306 ms wurden Schwarz abgezogen, passend zu 190305 ms Suche minus
2000 ms Inkrement und rund 1 ms weiterer Laufzeit.
Das bestätigt die schwarze Zeitabrechnung für diesen Zug, aber erklärt
noch keine falsche Anzeige während der Suche. Weiß hat bis zum nächsten
Suchauftrag außerdem einen weiteren eigenen Zug gemacht.
Im gesamten Log fehlt `setoption name UCI_Elo`; die Engine meldet
den Standardwert 1500.
