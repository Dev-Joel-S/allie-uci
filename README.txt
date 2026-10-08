EXPERIMENTAL: generated from source inspection; not tested by the author on NixOS.

Run allie-uci --test for actual model/UCI tests.
Run allie-uci --game for a complete game against Stockfish; may take many minutes.
Logs and PGN: test-results/. A failing test exits nonzero.
No GUI test is automated; import allie-uci as a local engine in En Croissant.

Model: real Allie 2.0, CPU int8, Rust KL search, upstream calibrated parameters.
Weights: about 11 GB download; allow additional disk and RAM for loading/builds.
Nix runtime and Allie source are pinned. Model revision and Python versions are
recorded during installation. Python transitive dependencies are not pre-locked.
FHS uses bubblewrap and requires working unprivileged user namespaces.

UCI_Elo: Allie's conditioning rating, 800..2600; not a newly measured Elo guarantee.
OpponentElo: opponent's rating; 0 mirrors UCI_Elo.
BaseTime: INITIAL seconds per side (e.g. 180 for 3+2); 0 means unknown.
MoveOverhead: milliseconds reserved for GUI/transport, default 100.
ALLIE_THREADS environment variable selects inference threads before startup.

UCI clocks arrive in milliseconds; Allie's inputs use seconds.
UCI does not supply the original base time, historical clocks, or the amount
added at a later time-control stage. BaseTime must be set for the actual game.
Observed clocks are retained; missing historical values use upstream interpolation.
Time-control changes, delayed snapshots, asymmetric increments and subsecond
increments are approximations outside the upstream calibration guarantee.
Different increments are used for timing/features; the single model header
represents them as unknown.
Clock observations at search start are not exact post-move timestamps.

Only standard chess with full history from startpos (or starting FEN) is supported.
Arbitrary FEN / Chess960, searchmoves, depth and mate limits are NOT supported.
Use clock-based play or movetime in En Croissant, not fixed-depth analysis.
Unsupported go commands fail with a diagnostic and nonzero exit.
nodes bounds requested KL leaf evaluations, not traditional alpha-beta nodes.
infinite/ponder retain one calibrated result until stop/ponderhit; they do not
provide unlimited-depth analysis. Ponder is advertised as disabled.
Resignations/draw offers are disabled because standard UCI does not convey them.

stop cancels between native KL batches and interrupts the simulated think wait.
It cannot preempt a model forward, initial loading, allocation or prefix prefill.
No hard real-time deadline or subsecond response guarantee is made.
The reader blocks during initial model loading; uci itself does not load weights.
A zero-leaf decision may occur legitimately when the calibrated time budget is
too small or a move is forced. Missing Rust backend is always a fatal error.
No fallback to another chess engine is used. Stockfish is only the test opponent.
