# Allie 2.0 UCI für NixOS

Experimenteller UCI-Adapter für **Allie 2.0** und **En Croissant** auf **NixOS x86_64**.

Der Adapter verwendet Allies vorhandenen **Calibrated Mode mit der Rust-KL-Suche**. Er ersetzt die Engine nicht durch Stockfish. Stockfish wird ausschließlich als Gegner im Partietest verwendet.

> **Teststatus:** Diese Umsetzung wurde anhand des Quellcodes vorbereitet, aber noch nicht auf NixOS ausgeführt. Installation, Modelltests, vollständige Testpartie und En-Croissant-GUI-Test sind bislang **nicht bestätigt**. Die mitgelieferten Tests laufen auf deinem Rechner; fehlgeschlagene Tests liefern einen Exit-Code ungleich null.

## Installation

Das gesamte Repository herunterladen oder klonen – `install.sh` benötigt die übrigen Dateien aus diesem Verzeichnis.

```bash
git clone https://github.com/Dev-Joel-S/allie-uci.git
cd allie-uci
bash install.sh
```

Alternativ auf GitHub **Code → Download ZIP** auswählen, entpacken und im entpackten Verzeichnis `bash install.sh` ausführen.

Voraussetzungen:

- NixOS / Linux auf x86_64 mit `nix-build`.
- Internetzugang für Nix-Pakete, Python-Abhängigkeiten und Modellgewichte.
- Etwa **11 GB allein für den Modell-Download**, zusätzlich Platz für Abhängigkeiten und Build-Dateien.
- Ausreichend RAM für Laden und Suche; eine feste Mindestgröße wurde hier nicht gemessen.
- Funktionierende unprivilegierte User-Namespaces für die FHS-/Bubblewrap-Umgebung.

Das Skript installiert ohne `sudo` standardmäßig nach:

```text
${XDG_DATA_HOME:-$HOME/.local/share}/allie-uci-0aace9ab
```

Es baut eine Nix-FHS-Umgebung und die Rust-Erweiterung, lädt die echten Modellgewichte und führt Parser- sowie Modell-/UCI-Tests aus. Ein vorhandenes Installationsverzeichnis wird nicht überschrieben.

Ein anderes Ziel ist möglich:

```bash
bash install.sh /absoluter/pfad/allie-uci
```

## In En Croissant verwenden

1. Nach erfolgreicher Installation **Engines → Add New → Local** öffnen.
2. Als **Binary** die vom Installer ausgegebene Datei `allie-uci` auswählen.
3. `UCI_Elo`, `OpponentElo` und `BaseTime` für die Partie einstellen.
4. Mit Uhrzeiten oder einer festen Zeit pro Zug spielen; **keine feste Suchtiefe** wählen.

Bei Standardinstallation ist die Engine-Datei:

```text
~/.local/share/allie-uci-0aace9ab/allie-uci
```

Im Dateidialog gegebenenfalls den vollständigen Pfad zu deinem Benutzerverzeichnis verwenden. **Nicht `install.sh` als Engine auswählen.**

Der konkrete GUI-Ablauf und die Einbindung wurden hier noch nicht praktisch getestet.

## Startskript

Vom Repository-Verzeichnis aus:

```bash
bash start.sh
```

Die Engine wartet dann auf UCI-Kommandos. Das ist kein interaktives Schachbrett; normalerweise startet En Croissant den Prozess.

Bei einem eigenen Installationsziel:

```bash
ALLIE_UCI_HOME=/absoluter/pfad/allie-uci bash start.sh
```

Optional lässt sich die Threadzahl vor dem Start festlegen:

```bash
ALLIE_THREADS=8 bash start.sh
```

## Optionen

| Option | Bedeutung | Standard |
|---|---|---|
| `UCI_Elo` | Allies konditioniertes Rating, 800–2600 | 1500 |
| `OpponentElo` | Gegnerisches Rating; 0 übernimmt `UCI_Elo` | 1500 |
| `BaseTime` | **Ursprüngliche** Sekunden pro Seite; 0 = unbekannt | 180 |
| `MoveOverhead` | Reserve für GUI/Transport in Millisekunden | 100 |

Beispiele: Bei **3+2** ist `BaseTime=180`, bei **10+5** ist `BaseTime=600`. Das Inkrement kommt aus den UCI-Kommandos der GUI.

Das eingestellte Elo ist ein Eingabewert für Allie, keine durch diese Integration neu vermessene Spielstärkegarantie.

## Tests und Protokolle

```bash
bash start.sh --unit
bash start.sh --test
bash start.sh --game
```

- `--unit`: Positionsparser, vollständige Zugfolgen, Rochade, en passant, Umwandlung, Mattstellung und Zeitparameter.
- `--test`: echte Modellgewichte und Rust-Backend; UCI-Handshake, legale Züge, ausgewertete Rust-Suchblätter, `isready` während einer Suche, `stop` und Partieende. Ziel des enthaltenen Stop-Checks: unter zwei Sekunden auf der geprüften, bereits geladenen Stellung.
- `--game`: vollständige Partie mit Allie als Weiß gegen Stockfish. Allie erhält 600+5, Stockfish rechnet 50 ms pro Zug. Eine Zeitüberschreitung oder das Erreichen der Halbzuggrenze ohne Partieende zählt als Fehler. Dieser Lauf kann viele Minuten dauern.

Die Installation startet `--unit` und `--test` automatisch. Die vollständige Partie wird separat mit `--game` gestartet.

Im Installationsverzeichnis entstehen:

- `install.log`, `unit-tests.log`, `model-tests.log`
- `test-results/uci.log`, `test-results/stderr.log`
- `test-results/python-chess.log`
- `test-results/game.pgn` beim Partietest

Vorhandene Testprotokolle können beim erneuten Lauf überschrieben bzw. ergänzt werden. Eine PGN mit Ergebnis `*` belegt keine abgeschlossene Partie.

**Noch ausstehend:** tatsächliche Ausführung dieser Tests und ein manueller En-Croissant-Test unter NixOS. Eine bestandene Testpartie wäre außerdem kein Nachweis einer bestimmten Elo-Spielstärke.

## UCI-Unterstützung und Grenzen

Vorhanden sind `uci`, `isready`, `setoption`, `ucinewgame`, vollständige `position`-Zugfolgen, `go` mit `wtime`, `btime`, `winc`, `binc`, `movetime`, `movestogo` und `nodes` sowie `stop` und `quit`.

- Unterstützt wird Standardschach ab `startpos` oder der **Anfangs-FEN**, jeweils mit vollständiger Zugfolge.
- Beliebige FEN-Stellungen, Chess960, `searchmoves`, `depth` und `mate` werden **nicht unterstützt**. Nicht unterstützte Suchanforderungen werden mit einer Diagnose abgebrochen.
- `nodes` begrenzt angeforderte KL-Blattauswertungen; das ist keine Alpha-Beta-Knotenzahl.
- `infinite` / `ponder` halten ein kalibriertes Ergebnis bis `stop` / `ponderhit`; es gibt keine unbegrenzt fortgesetzte Analyse. Ponder wird als deaktiviert angekündigt.
- Aufgaben und Remisangebote sind deaktiviert.
- Ein fehlendes Rust-Backend ist ein Fehler. Null Suchblätter können hingegen bei zu kleinem Zeitbudget oder einem erzwungenen Zug legitim sein.
- Die Modell-Kontextlänge begrenzt die übergebene Partiegeschichte.

### Zeitinformationen

[Standard-UCI](https://backscattering.de/chess/uci/) liefert aktuelle Restzeiten und Inkremente in Millisekunden sowie gegebenenfalls `movestogo`. Es liefert keine vollständige historische Uhrzeitfolge, kein eigenes Feld für die ursprüngliche Grundbedenkzeit und nicht die Höhe späterer Zeitgutschriften.

Deshalb muss `BaseTime` passend eingestellt werden. Fehlende historische Uhrstände werden mit Allies vorhandener Interpolation ergänzt und sind **Schätzungen**. Uhren beim Suchbeginn sind außerdem keine exakten Nach-Zug-Zeitstempel.

Unterschiedliche Inkremente werden für die Zeitverwaltung und die Uhrmerkmale berücksichtigt. Der einzelne Inkrementwert im Modellheader bleibt dabei unbekannt. Mehrphasige Zeitkontrollen sowie unterschiedliche oder untersekündliche Inkremente sind nicht durch eine neue Kalibrierung validiert.

### Suchabbruch

Der Rust-Patch ergänzt ein atomares Stop-Signal, das zwischen KL-Suchbatches geprüft wird. Der Adapter führt nur eine Suche pro Prozess gleichzeitig aus.

Ein einzelner Modelllauf, Speicherallokation, Modellladen oder das Einlesen einer langen Zuggeschichte kann nicht mitten in der Operation unterbrochen werden. Es gibt **keine harte Echtzeitgarantie**. Während des ersten Modellladens blockiert der Eingabeleser; das `uci`-Kommando selbst lädt noch keine Gewichte.

## Dateien

| Datei | Zweck |
|---|---|
| `install.sh` | Installation und automatische Modell-/UCI-Tests |
| `start.sh` | Start der installierten Engine |
| `engine.py` | UCI-Adapter |
| `test.py` | Parser-/Modelltests und vollständige Testpartie |
| `build.sh` | Abhängigkeiten, Rust-Patch, Build und Modell-Download |
| `environment.nix` | Nix-FHS-Umgebung |
| `run.sh` | Aufruf innerhalb der Laufzeitumgebung |
| `README.txt` | Technische Hinweise, auch im Installationsverzeichnis |
| `LIESMICH.txt` | Kurzanleitung |

## Upstream und Versionen

- [Offizielles Allie-Repository](https://github.com/y0mingzhang/allie), festgelegter Commit `0aace9abefbd75a24e3a1fd37e9dd1d3f992435b`.
- [Allie-2.0-Gewichte](https://huggingface.co/yimingzhang/allie-2.0). Die beim Installieren aufgelöste Revision wird in `model-revision.json` festgehalten.
- Nixpkgs-Commit `e7439b6b14ad3cc35d05608ebca9bce01a25f5f8`.
- CPU-PyTorch `2.10.0`; weitere tatsächlich installierte Python-Versionen stehen in `installed-requirements.txt`. Transitive Python-Abhängigkeiten sind nicht vorab vollständig gesperrt.
- Der angewandte Rust-Abbruchpatch wird als `upstream.patch` gespeichert.

Die Quellen und Gewichte verbleiben bei ihren ursprünglichen Lizenzbedingungen. Dieses Repository lädt Allie bei der Installation herunter und enthält keine Modellgewichte.

## Rust-Modul reparieren

Bei `No module named allie_fast` oder einer inkompatiblen Rust-Schnittstelle:
Aktuelles Repository herunterladen oder mit `git pull` aktualisieren, dann im
Repository-Ordner ausführen:

```sh
chmod +x repair.sh
./repair.sh "$HOME/.local/share/allie-uci-0aace9ab"
```

Das baut das gepinnte Rust-Modul erneut und installiert es in
`python-packages`. Startskript und Testprozesse verwenden denselben expliziten
Importpfad. Vor dem Modelldownload werden Modulpfad, INTERFACE=2 und alle
benötigten Symbole einschließlich des Stop-Patches geprüft. Bestehende Gewichte
werden weiterverwendet. Der Reparaturlauf führt anschließend die echten
Modell/UCI-Tests aus und bricht bei Fehlern ab.

```sh
"$HOME/.local/share/allie-uci-0aace9ab/allie-uci" --diagnose
```

`--diagnose` prüft nur die native Erweiterung; es beweist keine funktionierende
Modellinferenz. Das Modul `allie_fast` exportiert kein `fast`: Dieses Attribut
gehört zu Allies Modellinstanz. Ein Fehler dazu benötigt den vollständigen
Traceback; dieser wird jetzt in `test-results/stderr.log` gespeichert.

Die CI baut die echte Rust-Erweiterung unter Linux und prüft Import, Stop-Patch
und Parser. NixOS, En Croissant und eine vollständige Partie mit Modellgewichten
müssen weiterhin auf dem Zielsystem getestet werden.
