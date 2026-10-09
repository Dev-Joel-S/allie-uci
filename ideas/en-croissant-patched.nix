{ pkgs ? import <nixpkgs> {} }:

# Rebuild En Croissant; never modify a path inside /nix/store.
assert pkgs.lib.assertMsg (pkgs.en-croissant.version == "0.15.1")
  "This patch was tested against En Croissant 0.15.1; your nixpkgs contains a different version.";
pkgs.en-croissant.overrideAttrs (old: {
  patches = (old.patches or []) ++ [ ./en-croissant-clock.patch ];
})
