# Private OCI image delivery proposal

Status: source-only preflight, not an enabled publisher or deployment contract.
No registry package, credential, secret, paid resource or target was changed.
The existing qualification workflow remains unchanged. The failed archive
publisher is disabled: both canonical compressed images exceeded its consumer
limit. Do not split archives or repeat compression attempts.

## Observed capability and missing access

The public repository is `joshyorko/linkedin-easy-apply`. Its current operator
connection reports repository administration and push permissions, but a
read-only container-package inventory returned HTTP 403 requiring
`read:packages`. Repository access does not establish package access. No OCI
registry publisher or existing package reference is configured in this repo.
The repository's default workflow-token permission is read-only; workflow
approval of pull-request reviews is disabled. No package-write grant was tested.
No target credential or registry access was inspected; this phase excludes
the live target entirely.

GHCR is the proposed route because GitHub Actions can publish with its scoped
`GITHUB_TOKEN` and consumers can pull immutable digests. An existing approved
private package with explicit repository Actions access is preferred. Its
visibility and grants must be read back before any writer is enabled; never
infer them from this public repository or automatically create a package.

GitHub currently states that Container registry storage and bandwidth are free.
That does not authorize paid Actions capacity, another registry, or a future
billing change. The proposed native ARM64 hosted runner is the same class used
by existing qualification, with a bounded job timeout. Recheck policy before
enabling publication and stop if it introduces charges.

Sources: [GHCR authentication and digest pulls](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry),
[GitHub Packages billing](https://docs.github.com/en/billing/managing-billing-for-your-products/managing-billing-for-github-packages).

## Proposed reviewed workflow

Enable a publisher only after the private package and permission gates below
are satisfied. It should be manually dispatched from reviewed main, with no
pull-request publication. Use the existing pinned checkout action with
`persist-credentials: false`, fixed application source
`2bcca19b0eff40bdd14808fbb1e951fb126184ba`, and the existing
`qualification/Dockerfile` application target. Require a clean checkout and
native `linux/arm64`. The application source must not be edited during the build.

The fixed build uses CPython 3.12.11, Actions Runtime 1.1.2 and actions-core 1.1.0.
The ARM64 runtime wheel SHA256 is
`6ba7796dc2520fbffe12e9c023efb915144a2dda0b1865e0d12dd1faaf421a7d`.
The Dockerfile verifies this wheel and imports public package version 0.0.2.
Do not substitute the historical root Dockerfile or the synthetic fixture target.

Use a separate publication job with only `contents: read` and `packages: write`.
Keep build-only jobs read-only. Login with the job's ephemeral `GITHUB_TOKEN`
through stdin and an ephemeral Docker configuration, removed on exit. Do not
add a stored writer PAT, export a token, print auth data or reuse the publisher
credential on the target. Pin any new third-party action to a reviewed full SHA.

Before login/push, query the approved existing package metadata and fail unless
its visibility is private and this repository has the required Actions grant.
Do not automatically change visibility, grant access or create a package.
Push an identifiable source/run/attempt tag for discovery only. Resolve the
registry manifest digest from the push result and independently read it back.
All acceptance and deployment references must use `approved-image@sha256:...`,
never a tag. Verify the selected manifest/config declares `linux/arm64`, and
bind its config digest to the built Docker image ID. A manifest digest and a
Docker image/config ID are different identities and must both be retained.

Publish small provenance as a normal Actions artifact: repository, fixed
application source revision, reviewed workflow revision, run ID/attempt,
Dockerfile hash, complete checkout-source hashes, packaged `package.yaml` and
`src/` hashes read back from the image, startup-script hash, OCI source/revision
labels, config digest, registry manifest digest, media type and platform.
Verify the packaged source and startup script before publishing. No profile,
database, credential, private consumer source or host configuration belongs in
the image or provenance. Registry delivery removes the large ZIP dependency;
it does not remove immutable-byte verification or normal review.

## Target pull and acceptance gate

No target action is part of this proposal. In a separately authorized bounded
phase, first establish existing private registry read access through the normal
target process. Prefer an already-approved dedicated identity limited to this
package, with pull/read access only. GitHub documents a classic PAT with
`read:packages` for external private pulls; do not assume a fine-grained PAT or
repository credential works. If no approved local credential exists, stop at
that exact provisioning gate. Do not transfer a developer token, Actions token,
secret file or private source to make the pull work.

The target must independently pull the reviewed manifest digest, verify the
platform/config/source/provenance and retain the receipt. Test only disposable
synthetic peer, database and worker resources. The next cold test must make the
Rails client the first recorded-export caller, then test warm and first-call
after restart of only that owned disposable peer. Keep seeded durable replay,
production promotion and real sign-in as distinct gates. Existing services,
profiles, volumes, ingress and bundled integration stay untouched.

## Artifact and rollback contract

The handoff must name the exact reviewed workflow SHA, application source SHA,
run/attempt, package reference, private visibility verification, manifest digest,
config digest, `linux/arm64` platform and small provenance-artifact digest.
Neither an unverified tag nor the old receipt-only fixture artifact qualifies.
There is no registry artifact identity yet.

Keep the existing deployed image, source, persistent volume and rollback receipt
until independent consumer acceptance and a separately reviewed promotion pass.
The OCI candidate is initially disposable only. A future promotion must record
both old and new immutable identities, preserve the existing volume, and make
rollback restore the previous exact image/configuration without replaying
synthetic fixtures or transferring a browser profile. Do not delete a previous
registry digest needed for rollback. No production replacement, schema rollback,
bundle deletion or login is authorized by publishing an image.

Concrete remaining gates: package metadata access; verification of an existing
approved private package and repository publication grant; confirmation that
the target already has an approved package-read identity; normal review and
explicit enabling of the writer; exact native image publication and independent
digest/provenance verification. Package access is currently unproven, so this
proposal deliberately contains no executable registry writer.
