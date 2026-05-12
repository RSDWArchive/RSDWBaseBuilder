# RSDW Base Builder

A Blender add-on that lets you design Runescape: Dragonwilds bases visually
and load them straight into the game via RSDW Dev Kit.

**Recommended Blender version: 5.0.0 or newer** (this is what we build and
test on).

---

## What it does

- **Browse every base-building piece in the game** from Blender's Asset
  Browser. Walls, foundations, roofs, crafting stations, decorations,
  banners, farm plots — all there, organized in folders.
- **Drag and drop** pieces into your scene to design a base.
- **Snap pieces together** automatically while you build (just like in-game).
- **Save your design** as a `.json` file the in-game companion mod reads.
- **Load existing bases** from the `.json` files saved by the in-game mod
  and edit them in Blender.

If you can drag an icon, you can use this. No coding, no Blender knowledge
required beyond moving things around.

---

## Install

1. Download the latest `rsdw_base_builder-<version>.zip` from the releases
   page.
2. Open Blender (5.0 or newer).
3. Go to **Edit → Preferences → Get Extensions → Install from Disk…** (the
   little dropdown arrow in the top-right of the Extensions page).
4. Pick the `.zip` file you downloaded.
5. That's it. The asset library registers itself automatically.

---

## Quick start

1. Open Blender.
2. In the top toolbar, find the **RSDW** sidebar (press `N` in the 3D
   viewport if you don't see it, then look for the **RSDW** tab on the
   right side).
3. Click **New Basebuilding File…** and pick where to save it. This makes
   you a fresh, clean Blender file ready for designing — the original
   template is never touched.
4. Open Blender's **Asset Browser** (drag the bottom of the screen up to
   reveal a new editor area, then change its type to *Asset Browser*).
5. In the Asset Browser's library dropdown (top-left), choose
   **RSDW Base Builder**.
6. Pick a category (Building, Decorations, Farming, etc.), then drag any
   piece into the 3D viewport. Pieces snap to other pieces automatically.
7. When your base looks good, click **Export Building JSON…** in the
   **RSDW** sidebar. Save the file somewhere the in-game mod can find it.
8. In-game, the companion mod loads the `.json` and your character starts
   building.

---

## The RSDW sidebar — what each button does

| Button | What it does |
|---|---|
| **New Basebuilding File…** | Copies a clean template `.blend` to wherever you want and opens it. Use this every time you start a new design. The original template is never modified — you can't break it. |
| **Import Building JSON…** | Loads an existing base from a saved `.json` file so you can edit it. |
| **Export Building JSON…** | Saves your current design to a `.json` file the in-game mod can read. |
| **Anchor — Set Selected as Anchor** | Picks one piece as the "starting point" of the base. The game uses this to know where to begin building. Pick the most central or important piece (usually the foundation). |
| **Anchor — Select / Clear** | Highlights the current anchor in the viewport, or removes the anchor assignment. |
| **Move Selected to New Collection** | Takes the pieces you have selected and puts them into a new group (called a "Collection" in Blender). Handy for organizing big bases — e.g., put all your roof pieces in one group so you can hide them while you work on the floor. |

---

## Hotkeys

The add-on registers an editable 3D View shortcut for the diagnose helper:

| Action | Default shortcut | Operator ID |
|---|---|
| **Auto-Snap Selected to Nearest** | `Ctrl` + `Alt` + `D` | `rsdw.diagnose_auto_snap` |

To change it, open **Edit → Preferences → Keymap** and search for the
operator ID or the action name.

---

## Tips

- **Designs auto-snap** to neighbouring pieces. To place something freely,
  hold the standard Blender move tool and just position it manually.
- **Hide pieces** to keep them in the design but skip them during export
  (use the eye icon in Blender's outliner).
- **Use Collections** to organize floors, wings, or themed sections of
  your build. The Move Selected to New Collection button is the fastest
  way.
- **The anchor matters.** Always set one before exporting, otherwise the
  game won't know where to start building. The button errors out if you
  forget.

---

## What's inside the add-on

(For the curious — you don't need to know this to use it.)

- **One `.blend` file per piece**, in folders named for the in-game
  category (`Building/`, `Crafting_Stations/`, `Decorations/`, `Farming/`,
  `Furniture/`, `Misc/`).
- **`templates/basebuilding.blend`** — the clean starter file the
  *New Basebuilding File* button copies.
- **`blender_assets.cats.txt`** — the category tree the Asset Browser
  shows.
- Each piece is a self-contained `.blend` — base-color textures only,
  baked down to keep download size reasonable.

---

## Troubleshooting

- **"RSDW Base Builder" doesn't show up in the Asset Browser library
  dropdown.** Restart Blender after installing. If still missing, open
  **Edit → Preferences → File Paths → Asset Libraries** and add the
  add-on's install folder manually.

---

## Credits

Built for the Dragonwilds Creative & Sharing Hub (Discord)
Created by Hi im Tat