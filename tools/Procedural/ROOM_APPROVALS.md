# Procedural Room Approval Tracker

Last updated: 2026-06-10

This tracker records approval status for shape-lab room generation samples. The JSON files are generated under `_build/procedural/` and are not intended to be committed.

## Approved

| Room type | Approval sample | Pieces | Notes |
| --- | --- | ---: | --- |
| `l-shaped-tower-room` | `_build/procedural/approval_l_shaped_tower_room_t3.json` | 376 | Approved by review. |
| `ring-balcony-room` | `_build/procedural/approval_ring_balcony_room_t3.json` | 477 | Approved by review. |
| `split-level-gallery-room` | `_build/procedural/approval_split_level_gallery_room_t3.json` | 274 | Approved by review. |
| `square-tower-room` | `_build/procedural/approval_square_tower_room_t3.json` | 297 | Approved by review. |
| `square-vertical-room` | `_build/procedural/approval_square_vertical_room_t3.json` | 195 | Approved by review. |
| `switchback-tower-room` | `_build/procedural/approval_switchback_tower_room_t3.json` | 413 | Approved by review. |
| `u-shaped-tower-room` | `_build/procedural/approval_u_shaped_tower_room_t3.json` | 423 | Approved by review. |

## Pending Re-Review

| Room type | Approval sample | Pieces | Notes |
| --- | --- | ---: | --- |
| `hex-hybrid-atrium` | `_build/procedural/approval_hex_hybrid_atrium_t3.json` | 108 | First version was not approved for being too simple/symmetrical. Current sample is a vertical v2 with face-connected half-hex triangle bays, stair, upper landing, and elevated exit. |

## Pending Review

| Room type | Approval sample | Pieces | Notes |
| --- | --- | ---: | --- |
| `chamfered-hall` | `_build/procedural/approval_chamfered_hall_t3.json` | 201 | Vertical v2 generated for review with face-connected half-hex triangle bays, stair, upper landing, elevated exit, and two-wall-tall exterior edges. |
| `diamond-hall` | `_build/procedural/approval_diamond_hall_t3.json` | 154 | Vertical v2 generated for review with face-connected half-hex triangle bays, stair, upper landing, elevated exit, and two-wall-tall exterior edges. |
| `split-gallery` | `_build/procedural/approval_split_gallery_t3.json` | 186 | Vertical v2 generated for review with face-connected half-hex triangle bays, stair, upper landing, elevated exit, and two-wall-tall exterior edges. |
| `hex-cluster` | `_build/procedural/approval_hex_cluster_t3.json` | 146 | Vertical v2 generated for review with face-connected half-hex triangle bays, stair, upper landing, elevated exit, and two-wall-tall exterior edges. |
| `faceted-room` | `_build/procedural/approval_faceted_room_t3.json` | 147 | Vertical v2 generated for review with face-connected half-hex triangle bays, stair, upper landing, elevated exit, and two-wall-tall exterior edges. |
| `obtuse-hex-room` | `_build/procedural/approval_obtuse_hex_room_t3.json` | 151 | Vertical v2 generated for review with face-connected half-hex triangle bays, stair, upper landing, elevated exit, and two-wall-tall exterior edges. |
| `obtuse-hex-suite` | `_build/procedural/approval_obtuse_hex_suite_t3.json` | 331 | Vertical v2 generated for review with face-connected half-hex triangle bays, linked chamber footprint, two stair climbs, upper landings, and elevated exit. |
| `obtuse-hex-greatroom` | `_build/procedural/approval_obtuse_hex_greatroom_t3.json` | 356 | Vertical v2 generated for review with face-connected half-hex triangle bays, large faceted footprint, open center, two stair climbs, and elevated exit. |

## Review Rules

- Approved samples should keep zero narrow, small, or medium wall pieces unless a future room type intentionally needs them.
- Exterior room edges should be at least two walls tall; doorframes belong on the lower layer with a full wall-style piece above.
- Triangle floor extensions must be connected by full shared faces. Single triangle caps and tip-only triangle contact are not valid room floor connections.
- Doorframes should represent actual entrance or exit openings.
- Elevated stair support pieces should not appear visually unsupported.
- Approved room types can later be promoted from `shape-lab` into room-maze generation.
