# S10 policy migration for ArtisanROM 4.0.1

ArtisanROM 3.1.0 selected `dvfs_policy_makalu_xx` but did not store the newer
per-target `dvfs/siop_model.xml` input. The 4.0.1 DVFS module requires that
input when switching from the S24+ source's SIOP policy to an S10 policy.

The XML files under each S10 target's `dvfs` directory are unchanged Samsung
SDHMS resources. They come from the pinned S10+ firmware dump at
[leddaz-dump-stash/samsung_beyond2_dump](https://github.com/leddaz-dump-stash/samsung_beyond2_dump/tree/ed4c525d91f1c7f708296f345732a21935f28da8),
whose SDHMS APK contains separate Exynos9820 S10e, S10, S10+ and S10 5G
policies. No temperatures, clock limits, sensor expressions or scenarios
were edited. `dvfs-stock.json` records the APK Git blob, APK SHA256, original
resource names and every extracted XML's SHA256.

Preflight checks the stock digests and configured selectors for all four
models. Package validation compares the rebuilt SDHMS assets and DVFS raw
resource against these inputs, checks both generic default policies, rejects
leftover encrypted source policies and checks the floating-feature selector.
The SDHMS APK is also checked inside the actual ext4 image.

The S10 VINTF device compatibility matrix is imported from each build's own
extracted target firmware. Its requirements describe the stock vendor HALs;
they are not copied from the S24+ vendor contract. Import validates the XML
and required S10 contracts, preserves its bytes, and records its digest,
device and firmware identity. Packaging rechecks that record and the actual
ext4 contents. The source's Android 16 framework manifest is retained.

These checks validate build inputs and packaged contents. Physical boot,
temperature behaviour and hardware operation still require device testing.
