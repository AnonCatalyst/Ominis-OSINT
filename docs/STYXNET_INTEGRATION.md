# StyxNet integration

StyxNet is the WinterGate Intelligence Collective's passive multi-surface OSINT platform. It uses Ominis page-inspection primitives as a downstream validation layer for profile-like search results.

## What StyxNet uses

- Page metadata and canonical URL
- Redirect confirmation
- Structured data and embedded JSON
- JSON-LD and microdata
- Author metadata and author links
- JavaScript state
- Entity/user activity linked to the handle

## Result states

- **Confirmed** — strong page-level linkage
- **Linkage-confirmed** — strong trace with limited corroboration
- **Unverified** — weak, missing, or rejected evidence

Confirmed results are prioritised in StyxNet. Weak profile-like results are demoted. Ordinary articles are not falsely labelled.

## Bounded validation

StyxNet validates a small number of profile-like candidates per search with bounded concurrency and timeouts. This keeps validation useful without making search latency unbounded.

## Scope

This is a documentation note for a downstream integration. It does not change Ominis' standalone CLI or workstation behaviour.

## Links

- StyxNet: https://github.com/WinterGate-IC/StyxNet
- StyxNet platform: https://wintergate.org/styxnet/
- Ominis-OSINT: https://github.com/AnonCatalyst/Ominis-OSINT
