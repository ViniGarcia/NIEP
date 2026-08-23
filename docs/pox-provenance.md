# Vendored POX provenance

NIEP keeps POX under `OFCONTROLLERS/pox/` as a deployment asset. It is not a
Python dependency of the `niep` wheel, and it is excluded from maintained-code
coverage, formatting and lint checks. Keeping it vendored preserves the
offline/reproducible VM workflow and the controller integration used by NIEP.

## Known provenance

- Upstream project: <https://github.com/noxrepo/pox>
- Upstream documentation: <https://noxrepo.github.io/pox-doc/html/>
- Upstream named Python 3 series identified by the vendored README: `gar`
- NIEP update/import commit: `19802a2aaa74a8630a6dc6b0f172264d4013e8c5`
- NIEP update commit date: 2026-06-13
- Direct parent of the NIEP update commit: `753143ddca501fb2f273bdd617bd2e557be1a114`
- Last earlier NIEP commit that touched POX: `9014a023860e829454fffb8d7a986650fdff752c`
- POX tree immediately before the update (`19802a2^` and `9014a02`):
  `535355262fe9270135c16ffd63f37e63a7699657`
- Historical POX ancestry also contains `4ee88b8f1241e85c7aa1bf1aa544c9c6b017da30`;
  it is not claimed as the immediate pre-update baseline.
- Update delta recorded by Git: 183 files changed, 6,944 insertions and 1,215
  deletions between `9014a02` and `19802a2` under `OFCONTROLLERS/pox/`.
- Current NIEP content tree object after the update:
  `9d2747111abeecb5f8ec4a2e2f6eea27e9cdb6ea`
- Canonical file-list/tree hash at that baseline:
  `480b40cdf498288ae85b019026c02fe9c2c4208b800de4f134d358d01a6f3d03`

The repository does not contain the exact upstream commit or archive hash from
which the 2026 update was obtained. This limitation is intentional and
auditable: the NIEP import commit, its parent, the last pre-update POX commit,
the before/after tree objects and the deterministic tree hash above are
recorded rather than inventing an upstream identifier. Future POX updates must
record the exact upstream ref, source archive SHA-256, retrieval date and a
machine-readable patch manifest before merge.

## Reproducing the current baseline

From a checkout containing the release commit:

```bash
git rev-parse HEAD:OFCONTROLLERS/pox
git rev-parse 19802a2^:OFCONTROLLERS/pox
git ls-tree -r --full-tree HEAD -- OFCONTROLLERS/pox | sha256sum
git diff --stat 9014a02 19802a2 -- OFCONTROLLERS/pox
git diff --name-status 9014a02 19802a2 -- OFCONTROLLERS/pox
git archive --format=tar HEAD -- OFCONTROLLERS/pox | sha256sum
```

The first two values are the post-update and pre-update content identifiers
used above. The diff commands reproduce the recorded import delta. The archive
hash also depends on archive metadata and is useful as a release artifact
fingerprint.

## Maintenance rules

1. Keep `LICENSE` and `NOTICE` with the vendored tree.
2. Do not include POX in the installable `niep` package.
3. Exclude POX from NIEP coverage, formatting and lint gates.
4. Record each upstream update as a separate commit when practical.
5. Record upstream ref/hash, local patch files, reason for every patch and
   validation commands in this document or a checked-in manifest.
