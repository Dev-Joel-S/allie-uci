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
