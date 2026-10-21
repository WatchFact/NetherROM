# S10 face HIDL 2.0 migration

This migration targets the original Samsung `services.jar` extracted from the
pinned 4.0.1 source firmware
`S926BXXSHDZI1/S926BOXMHDZI1/S926BXXSHDZI1`. Its SHA256 is
`0a7cd6f0e2ea163e48bc49056ba4ba7a12e97fa2b8b2afcded7a238e4d34d336`.
The exact JAR and decoded review inputs were obtained by
[Actions run 39543878061](https://github.com/WatchFact/NetherROM/actions/runs/39543878061),
using the SHA256-pinned S10 toolchain. These diagnostic inputs are not a ROM.

The generic legacy face patch targets an older R8 layout. In this source,
`AidlResponseHandler` initializes the existing `Lambda6` enrollment-cancellation
runnable through fields and a memory fence; the memory-authentication runnable
is `Lambda4`, and `Lambda5` is absent. The S10 patch retains the complete native
cancellation implementation and removes only the HIDL 3.0 authentication-memory
path. Legacy authentication uses `sehAuthenticate` on HIDL 2.0. AIDL handling is
preserved.

The migration selects the HIDL 2.0 service and callback registration, completes
the retained V2.0 proxy methods, and moves the source's security-level reply
callback into the V2.0 namespace. The latter class was not present under its
V2.0 name in the source and cannot simply be deleted along with the V3.0 stub.
The original interface transaction numbers are preserved: TestHal handles
transactions 1–34 and its callback handles 1–10. Only the final V3.0 transactions
are removed. Both interface chains and hash chains advertise the same three
interfaces: Samsung 2.0, Android Face 1.0 and IBase. The V2.0 and base hash bytes
come unchanged from the corresponding entries of the original source.

`face-hidl-v4.0.1.json` records the patch digest and 22 class fingerprints before
and after migration, including the unchanged enrollment-cancellation classes.
`face_hidl.py` rejects unknown source JARs, changed/ambiguous classes, obsolete
V3.0 references, missing abstract interface implementations, unresolved vendor
face types, and incompatible transaction/hash-chain sizes. The final audit
checks the rebuilt JAR's DEX class presence and rejects V3.0 face references.
The actual ext4 image is checked against the audited `services.jar`; migration
provenance is included in the flashable ZIP and Actions diagnostics.

Validation used the exact extracted source: strict `git apply --check`, patch
application, all four target guards, a fresh complete JAR assembly with the
pinned Apktool, the rebuilt-JAR audit, and negative checks for a changed
cancellation class and an incomplete proxy implementation. The existing ten
port regressions and all four 554-file hardware preflights also passed.

These checks establish source compatibility and build integrity. Face enrollment,
authentication, removal, and other hardware behavior still require physical S10
series device testing.
