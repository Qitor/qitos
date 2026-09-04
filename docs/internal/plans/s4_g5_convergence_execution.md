# S4 G5 convergence execution

Status: in progress; not qualified; no promotion authorized until all gates pass.

## Source lock

Baseline: `306e689ab19665678b6de644045d374c5ec05102`.
Common ancestor: `c4e621d05960a4e2f06cb4864f6a8cb8275ac067`.
Primary branch: `feat/campaign-absorption`; clean and exact at task entry.
Integration branch: `codex/v4-s4-g5-convergence`, created from baseline.
Four source worktrees were independently clean with exact branch/HEAD and
merge-base before replay. The C manifest SHA-256 is
`80f3db9514791738f699932e17a2dfab80c6190d1083d388493fa2bc523d6a49`.

| Lane | Fixed HEAD | Count |
| --- | --- | ---: |
| A | `f670e551f0bd5d88501182c2d24a5037fa0aebb9` | 5 |
| B | `c834ce76b939e86b33019719d5b212b1c7a38bdd` | 7 |
| C | `a1958fe620f9a80017d80aca702711991b80c8e6` | 10 |
| D | `18278bd42ea91284f76f2d4523f82d316cc20a75` | 7 |

## Execution sequence

1. Replay 29 commits A → B → C → D; resolve overlap semantically and recount interfaces.
2. Commit reproducible failing audit regressions, then fix C1/C2, A1/A2, B1, D1/D2/D3.
3. Complete composition, sandbox, artifact, Session/work, and Trajectory bindings.
4. Requalify historical/current facts and two independently installed consumers.
5. Qualify real Docker serially, full suite, quality, packaging matrix, measurements.
6. Freeze schema, switch writer and reader in distinct commits only after prerequisites.
7. Verify candidate, fast-forward local primary, repeat required primary gates.
8. Retain all worktrees/refs and record retirement inventory. No remote writes.

## Toolchain

Verified Python 3.12.7 at the requested interpreter; metadata: flake8 7.0.0,
mypy 1.19.1, pyflakes 3.2.0, pycodestyle 2.11.1, mccabe 0.7.0.
Additional installed tools: pytest 9.0.3, build 1.3.0, twine 6.2.0.
No shared environment was modified.

## Replay mapping (source → replay)

| Lane | Source SHA | Replay SHA |
| --- | --- | --- |
| A | `315f33f8476a9de5a9afbaaea8cede9c0624f63e` | `1938ea21acec891bc5b46c3c84cfd515fa317b5c` |
| A | `c3989afb5995d88d022ea9774398fb5b1396111c` | `aaeff0a0ce2f0d8f970ba1bb64741e460621efd5` |
| A | `bdaa8be1e49722c2cf647ee6f784493132ed29d8` | `442b7fa8ad9ef7c73768f8aa056f59cbb0aa8aa8` |
| A | `65718ee782065e7dccc3b3d0a5e7ea9a318b5411` | `839e6456d1acde999b0b680c47dce3cd1e219a18` |
| A | `f670e551f0bd5d88501182c2d24a5037fa0aebb9` | `96f504b0f018584bf46eb065ba1029f98cce8b70` |
| B | `5930b38d2c12532d9183ac8a375669fccd71c6d5` | `7e86a1157a0c3dd0689b3484c31b05dd48879c22` |
| B | `4a22cc5082f1fc63a500ba4c82cc53090016ccc3` | `b4ebab112c368d53fe00b708d5cce9852aecc8fb` |
| B | `e6ed17f7047a6dcbbc384cb8c46478090ac2f99d` | `23a165e7b0ade33152d74c8b3380efd0e3695e87` |
| B | `f77cbf6d80eec8622b613e4406f58702d2ac3828` | `0f2c000770c92358263092a74c41d79a0e1eb6d2` |
| B | `ba58a6b3169b5f68d3e4e220394078904d99de27` | `4aaa1389bad46814fcf055c3f731de87a6308da5` |
| B | `e83fca34dfa362a336fa5b2ff9d1cd659dbe5e8d` | `2f4ebc0cc4c609c163a6b67d44c8edb7c12e2e05` |
| B | `c834ce76b939e86b33019719d5b212b1c7a38bdd` | `d278c44dd414690ccd5eee988bcc5c601c090e84` |
| C | `bb154a1136104c6bec0d48be3a4860dae5bb5684` | `dd3084843f31a143c62a44ab685172c8a94e3de0` |
| C | `b24b3a66449feff8a2c6d2faa6a1a73b1e105441` | `7f839becd36c4c49161fb69a1d9b217ffbcf993f` |
| C | `6429d394ddb52ed6ec807b52edc42d62e90b5b31` | `ad53cbf59bc0a635e79d34be3643abc333977ceb` |
| C | `c194ad7e063f8c4c3f0b9f349670ba84027317bc` | `b1323c29a8285768fab1a9db3df0c6f93f46f191` |
| C | `7ba11147445277788135aa748c52454e7002bb59` | `b0bab586a2e085933029253b2d913d59bfab7346` |
| C | `7225a955f534fe0cf64c258369e78ca876df15cf` | `96895e8f54028fe7d2d8210a39766a184bbdc522` |
| C | `2ae2c23ebb5e651240e579d035fa10abdad3356a` | `5ecc1f494648c64b4da32b17476984f0b3dced0c` |
| C | `4f0d728462573bb4e0f91f3ed5516fa259d7e413` | `909f6ee1ff4e24ed80a071927941de6286b86901` |
| C | `3b46dfb43391da302afe0ab1bd2ca7a61df60dad` | `a39a917c10fd551ea63ce19f0317dee859f27199` |
| C | `a1958fe620f9a80017d80aca702711991b80c8e6` | `6b08da3188317810a4fb17b2aaa5553d062c84c7` |
| D | `d722d039d658a6251d93889cb1bb80f519fab3f6` | `b380af7712155a14fd7eec3ce28c9911bd3c2602` |
| D | `6b8982f7220e00cf282879823de06f7823b91207` | `29a571a9fe36595d5cd3e658cb2272517218a3c4` |
| D | `4798f39995f7cbd69684585dbfa17d2b80eeca16` | `3df69e760b8a13360b263c4f4d63ca0d56fb6381` |
| D | `0c4d7c39fb8293efd45dd3872c17786064e7be5a` | `37895d29a1a202baf2e9534b1423ec5ef7ac2e56` |
| D | `4f17c7c902b9fe6e749f8af52380fab8831f05cd` | `942bbbb9d7914c6f443a072aec13f8c38329532a` |
| D | `65df1ddd03108721e105d21b8415b5f8b959a0d6` | `ebf4f057f9de987c2fc65b158e8b831921415231` |
| D | `18278bd42ea91284f76f2d4523f82d316cc20a75` | `6c764522fccbab8a499aab6994d5a8bd82b7913f` |

## Conflict resolutions

A/B conflicted only on deliberate export totals in the interface budget JSON
and test. Imported each classified module and checked exact `__all__` membership:
artifact 6, session 44, request_view 25, tool_result 15, work_graph 22,
snapshot_composition 1, codec 14, config.errors 27, sandbox 10, diagnostics 0.
Total 164; internal-private 3; root exports 41; Engine signature unchanged.
No whole-file conflict selection or new interface was used.

A/C automatic merges retain the union of source test function names in
`tests/test_sandbox_backend_contract.py` and `tests/test_yaml_config.py`.

## Validation and repairs

No G5 repair or qualification has yet passed. Historical audit failures remain
unchanged in the audit document. No live provider calls or private credential
reads are authorized. Docker qualification must use only task-owned labels.
