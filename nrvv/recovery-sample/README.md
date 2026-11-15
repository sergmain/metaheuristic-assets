# recovery-sample

A very small Java project for NRVV's RECOVERY capability. It replaces the Apache Derby sample of plan 057 (NRVV v11),
whose processing needs far more tokens (the user, 2026-11-14).

A pricing office sets gas prices; stations display them. Four classes:

| File | Package | Role |
|---|---|---|
| `PriceChannel.java` | `sample.pricing.api` | the interface between the office and the stations - publish, poll, acknowledge |
| `Messages.java` | `sample.pricing.api` | the messages on the channel - `PriceUpdate` and `Ack`, with their validation |
| `Provider.java` | `sample.pricing.provider` | the office's side: numbers each station's updates, does not resend an unchanged price |
| `Consumer.java` | `sample.pricing.consumer` | a station's side: displays the newest fresh price, drops older or stale ones, acknowledges each |

The boundary is the package `sample.pricing.api` (RECOVERY's `boundaryPackages`): its files are on the system's boundary
by a deterministic signal. `Provider` and `Consumer` are classified by the model.

Source only, no build file: `javac -d <out> $(find src/main/java -name '*.java')` compiles it (Java 17 or later).
RECOVERY reads it at `nrvv/recovery-sample` on `master`, include glob `src/main/java/**/*.java`.
