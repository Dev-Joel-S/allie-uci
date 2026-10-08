let
  pkgs = import (builtins.fetchTarball {
    url = "https://github.com/NixOS/nixpkgs/archive/e7439b6b14ad3cc35d05608ebca9bce01a25f5f8.tar.gz";
  }) { system = "x86_64-linux"; config.allowUnfree = false; };
in pkgs.buildFHSEnv {
  name = "allie-env";
  targetPkgs = p: with p; [
    bash coreutils gitMinimal cacert python312 uv rustc cargo
    gcc gnumake pkg-config openssl zlib numactl maturin patchelf stockfish
  ];
  runScript = "bash";
}
