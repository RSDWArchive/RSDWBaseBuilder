# Procedural Room Approval Tracker

Last updated: 2026-06-10

This tracker records approval status for shape-lab room generation samples. The JSON files are generated under `_build/procedural/` and are not intended to be committed.

## Approved

| Room type | Approval sample | Pieces | Notes |
| --- | --- | ---: | --- |
| `l-shaped-tower-room` | `_build/procedural/approval_l_shaped_tower_room_t3.json` | 437 | Approved by review. Current sample includes connector hallways at all entrance/exit doorframes. |
| `ring-balcony-room` | `_build/procedural/approval_ring_balcony_room_t3.json` | 538 | Approved by review. Current sample includes connector hallways at all entrance/exit doorframes. |
| `split-level-gallery-room` | `_build/procedural/approval_split_level_gallery_room_t3.json` | 330 | Approved by review. Current sample includes connector hallways at all entrance/exit doorframes. |
| `square-tower-room` | `_build/procedural/approval_square_tower_room_t3.json` | 358 | Approved by review. Current sample includes connector hallways at all entrance/exit doorframes. |
| `square-vertical-room` | `_build/procedural/approval_square_vertical_room_t3.json` | 228 | Approved by review. Current sample includes connector hallways at all entrance/exit doorframes. |
| `switchback-tower-room` | `_build/procedural/approval_switchback_tower_room_t3.json` | 479 | Approved by review. Current sample includes connector hallways at all entrance/exit doorframes. |
| `u-shaped-tower-room` | `_build/procedural/approval_u_shaped_tower_room_t3.json` | 484 | Approved by review. Current sample includes connector hallways at all entrance/exit doorframes. |

## Pending Re-Review

| Room type | Approval sample | Pieces | Notes |
| --- | --- | ---: | --- |
| `hex-hybrid-atrium` | `_build/procedural/approval_hex_hybrid_atrium_t3.json` | 157 | First version was not approved for being too simple/symmetrical. Current sample is a vertical v2 with full six-piece hex triangle clusters, stair, upper landing, elevated exit, and connector hallways. |

## Square Room Crawl Experiments

| Preset | Sample | Pieces | Notes |
| --- | --- | ---: | --- |
| `square-room-crawl` | `_build/procedural/square_room_crawl_7_seed42.json` | 1059 | Compact square-room graph based on the older room-maze generator, using approved-room-inspired compact blueprints. No triangle floor pieces. |
| `square-room-crawl` | `_build/procedural/square_room_crawl_12_seed42.json` | 1670 | Larger compact graph sample with approved square/tower/gallery/atrium motifs, branches, loops, and no dangling doorframe exits. |

## Pending Review

| Room type | Approval sample | Pieces | Notes |
| --- | --- | ---: | --- |
| `chamfered-hall` | `_build/procedural/approval_chamfered_hall_t3.json` | 270 | Vertical v2 generated for review with full six-piece hex triangle clusters, stair, upper landing, elevated exit, two-wall-tall exterior edges, and connector hallways. |
| `diamond-hall` | `_build/procedural/approval_diamond_hall_t3.json` | 218 | Vertical v2 generated for review with full six-piece hex triangle clusters, stair, upper landing, elevated exit, two-wall-tall exterior edges, and connector hallways. |
| `split-gallery` | `_build/procedural/approval_split_gallery_t3.json` | 245 | Vertical v2 generated for review with full six-piece hex triangle clusters, stair, upper landing, elevated exit, two-wall-tall exterior edges, and connector hallways. |
| `hex-cluster` | `_build/procedural/approval_hex_cluster_t3.json` | 215 | Vertical v2 generated for review with full six-piece hex triangle clusters, stair, upper landing, elevated exit, two-wall-tall exterior edges, and connector hallways. |
| `faceted-room` | `_build/procedural/approval_faceted_room_t3.json` | 216 | Vertical v2 generated for review with full six-piece hex triangle clusters, stair, upper landing, elevated exit, two-wall-tall exterior edges, and connector hallways. |
| `obtuse-hex-room` | `_build/procedural/approval_obtuse_hex_room_t3.json` | 207 | Vertical v2 generated for review with full six-piece hex triangle clusters, stair, upper landing, elevated exit, two-wall-tall exterior edges, and connector hallways. |
| `obtuse-hex-suite` | `_build/procedural/approval_obtuse_hex_suite_t3.json` | 419 | Vertical v2 generated for review with full six-piece hex triangle clusters, linked chamber footprint, two stair climbs, upper landings, elevated exit, and connector hallways. |
| `obtuse-hex-greatroom` | `_build/procedural/approval_obtuse_hex_greatroom_t3.json` | 438 | Vertical v2 generated for review with full six-piece hex triangle clusters, large faceted footprint, open center, two stair climbs, elevated exit, and connector hallways. |

## Review Rules

- Approved samples should keep zero narrow, small, or medium wall pieces unless a future room type intentionally needs them.
- Exterior room edges should be at least two walls tall; doorframes belong on the lower layer with a full wall-style piece above.
- Triangle floor extensions must be complete six-piece hex clusters connected by full shared faces. Single triangle caps, half clusters, and tip-only triangle contact are not valid room floor connections.
- Doorframes should represent actual entrance or exit openings.
- Every entrance/exit doorframe should have a short connector hallway attached, with a walkable floor and a doorframe/opening at the far end for room linking.
- Elevated stair support pieces should not appear visually unsupported.
- Approved room types can later be promoted from `shape-lab` into room-maze generation.
