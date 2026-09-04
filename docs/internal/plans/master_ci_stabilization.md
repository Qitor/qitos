# Master CI stabilization after G5

Status: executing with explicit user authorization to unfreeze runtime code.
Starting master: f9e45f372ba4b8a5c89982add56a667908893b30.
Historical G5 qualification remains bound to
717b4cf1b23f2ed252cd03234ffd8605038d9567; successor tests are recorded separately.

## Plan

1. Read exact GitHub failures; reproduce publication under the Python 3.10 API
   surface before replacing file_digest with bounded descriptor-based hashing.
2. Restore portable access to exact historical qualification objects without
   substituting current bytes, weakening digests, or fabricating source identity.
3. Resolve any remaining runner/test/runtime failures based on observed evidence.
   Keep the Python matrix, coverage floor, audit, static baseline and security
   semantics intact. No live model, package publication, service deployment or
   ruleset change is authorized by this continuation.
4. Run focused regressions, complete local required gates where applicable, then
   ordinary push to master and preserved integration branch. Read GitHub checks
   for the final SHA and require actual successful completion before saying green.

All historical refs and external qualification archives remain preserved. Further
runtime changes belong to this successor, not to the historical G5 baseline.


## Publication regression

The two empty/multi-chunk regression cases first failed with AttributeError
when the Python 3.11-only hashlib.file_digest attribute was absent. The fix
reads the already verified descriptor in 256 KiB chunks and preserves before/
after fstat comparison, O_NOFOLLOW, regular-file/single-link checks and rollback.
Publication/input-staging/public-surface/architecture checks: 34 passed locally.
The full publication file including the regression has 21 passing cases.

## Historical Git objects

Twenty exact commits referenced by retained fixtures are absent from remote
history; ten maximal source tips cover them. A same-tree ancestry-retention
merge will keep their original Git objects reachable from master. This imports
no source-tree changes and does not replay or re-integrate G5 implementations.
Original source SHA/digest checks remain unchanged; no replacement evidence,
new archive binary, source-ref mutation or extra remote branch is needed.
The new commit tree must equal its first parent's tree byte-for-byte.

Prospective history scan: 70 commits, 404 distinct changed blobs. Of 50 pattern
matches, 48 blobs already occur in the remote object graph. The two other docs
blobs contain only local-path values already published in those same files;
comparison found zero newly disclosed path values. Secret-like inputs remain
known synthetic rejection fixtures. No new credential or private endpoint was
identified. No value is echoed into this report.

Maximal retained source commits:
- `cab8fd246d2485784a13558e668eadb3ffa4d42f`
- `f670e551f0bd5d88501182c2d24a5037fa0aebb9`
- `c834ce76b939e86b33019719d5b212b1c7a38bdd`
- `a1958fe620f9a80017d80aca702711991b80c8e6`
- `18278bd42ea91284f76f2d4523f82d316cc20a75`
- `9442647767bc9a7c45ed3bf07bc4f289412544ed`
- `5efa1db19ae541234c562c4ba99e928d2381fc62`
- `12edf48aa5dd2ed7c3c830baf9031116474bcc52`
- `bc725e8b77576a7a0b5c165a5066c83c4d9965c8`
- `60e8d94edb9a5f00434095a3489e1e1100185bea`
