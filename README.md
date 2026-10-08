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
