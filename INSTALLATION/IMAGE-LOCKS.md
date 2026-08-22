# Images and update policy

The Docker fixtures use the linux/amd64 Alpine 3.20 single-platform manifest.
The reproducible input currently verified with
`docker buildx imagetools inspect alpine:3.20` is:

```text
alpine:3.20@sha256:c64c687cbea9300178b30c95835354e34c4e4febc4badfe27102879de0483b5e
```

The exact reference is recorded in `image-locks.env`; every fixture Dockerfile
and Alpine container descriptor must use the same `tag@digest` (the doctor
rejects a mutable tag or a different digest). This digest is intentionally
amd64-only; build and run these fixtures on linux/amd64. The two
`niep/iperf3*` images are local build products, so their digest is not pinned
in source.

The normal doctor does not require local build products. To require both local
build products explicitly after their builds, run
`python3 tools/niep_doctor.py --check-local-images` (or combine it with
`--check-images`). The explicit check exits unsuccessfully if either image is
absent.

The provisioner caches the immutable Alpine reference before installing the
Python environment. `make check-images` requires that cache entry, so an
offline integration run fails during preflight instead of after resources have
already been created.

To update an image, deliberately choose a new immutable digest, verify it
with `docker buildx imagetools inspect` and `docker image inspect` (and a clean
fixture build), update
`image-locks.env` and this document together, then run `make check-images` and
the relevant integration test.  Never replace a digest with one inferred from
an unverified tag.  Git LFS qcow2 images are handled separately: use
`make lfs-pull`, then `make check-images` before any VM/integration test.
