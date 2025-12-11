# Demo 01 - Basic storage-collision detection

This demo shows STORAGELENS catching a real upgrade-unsafe storage change in
an upgradeable (proxy) contract.

## The contracts

**V1** (`old_layout.json`) declares, in order:

| slot | offset | var          | type        |
|------|--------|--------------|-------------|
| 0    | 0      | `owner`      | address     |
| 1    | 0      | `totalSupply`| uint256     |
| 2    | 0      | `paused`     | bool        |

**V2** (`new_layout.json`) was edited carelessly:

- `totalSupply` (slot 1) was **retyped** `uint256 -> uint128` (RETYPED, error)
- A new `feeRecipient` (address) was **inserted** at slot 2, shoving the
  original `paused` flag down (INSERTED_MIDDLE, error)
- `version` (uint256) was correctly **appended** at the end (APPENDED, info)

## What to run

```
python -m storagelens diff demos/01-basic/old_layout.json demos/01-basic/new_layout.json
python -m storagelens diff demos/01-basic/old_layout.json demos/01-basic/new_layout.json --format json
```

## Expected result

The tool reports the RETYPED and INSERTED_MIDDLE findings as `ERROR`
collisions and the appended `version` as a safe `INFO`. Because collisions
exist, the process exits with **code 1** so a CI gate fails the build.

A clean, append-only upgrade would exit `0`.
