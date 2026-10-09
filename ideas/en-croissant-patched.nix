{ pkgs ? import (builtins.fetchTarball {
    url = "https://github.com/NixOS/nixpkgs/archive/d261affe5e054396f3bf4ec799f304827b7f8b85.tar.gz";
  }) {} }:

# Use the verified package revision independently of the host's NIX_PATH.
assert pkgs.lib.assertMsg (pkgs.en-croissant.version == "0.15.1")
  "The explicitly supplied pkgs must contain En Croissant 0.15.1.";
pkgs.en-croissant.overrideAttrs (old: {
  patches = (old.patches or []) ++ [ ./en-croissant-clock.patch ];
})
