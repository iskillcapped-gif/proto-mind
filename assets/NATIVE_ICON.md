# Native Cube Icon

The personal Native application uses `proto_mind_native_icon.png`, a 1024 x 1024 RGBA master. The cube silhouette and three geometric glyphs reinterpret the operator-supplied emblem; the original wordmark and screenshot are not included. Graphite, petrol-teal glass, silver bevels and turquoise insets replace the original copper palette. This is a visual update only, not a product or provider identity change.

The artwork was created with the built-in image-generation tool, not an API-key workflow. Its returned PNG painted a checkerboard rather than supplying alpha. With the operator's explicit approval, local macOS Vision/Core Image foreground extraction removed that outside background, contracted the matte by seven source pixels to remove bright contamination, softened the matte by 0.35 pixels, and encoded the unchanged artwork as a 1024-pixel sRGB RGBA master. This was one-time asset preparation. Runtime and future builds do not use Vision or an image model.

## Packaging

```bash
scripts/build_native_icon.sh
scripts/build_native_app.sh
```

The first command creates `dist/ProtoMindCube.icns`. The Native app builder packages the same master into its own `Contents/Resources/ProtoMindCube.icns`, referenced by `CFBundleIconFile`. Apple's local `sips` and `iconutil` generate the standard ten 1x/2x representations from 16 to 1024 pixels. No legacy PySide build or network call is required. Temporary packaging files are removed; the source is not rewritten. The former `proto_mind_icon.svg` and PySide icon remain intact. After signing, the builder refreshes this app's timestamp and Launch Services registration; it never restarts Dock or clears shared icon caches.

`scripts/test_native.sh` checks master dimensions, real alpha, transparent corners, the opaque cube center and useful foreground coverage. The packaged ICNS is also round-tripped during release verification.

## Generation Prompt

```text
Use case: style-transfer / logo-brand.
Asset type: production macOS application icon for Proto-Mind, one square 1024 x 1024 RGBA image.
Reference: the attached screenshot is ONLY a geometry reference for the small gold isometric cube emblem near its upper middle. Extract the idea of that cube and its three simple inset geometric glyphs. Ignore ALL screenshot UI, all typography, the human head, the photographic surroundings and the original gold palette.
Primary request: reimagine that emblem as a tactile, beautifully dimensional premium app icon. Keep a single clearly readable isometric cube with three visible faces, a hexagonal outside silhouette, the Y-shaped junction of its thick raised bevelled edges, and simple sculpted inset angular glyphs inspired by the reference: a small angled top-face mark, a left-face L-shaped mark with one dot, and a right-face hooked angular mark. This should feel like the same family of emblem, not a generic glowing cube, die, Rubik cube or chip.
Materials: finely machined satin titanium/silver bevels framing deep translucent petrol-teal glass faces; dimensional luminous turquoise/mint inset glyphs, carefully controlled aqua edge reflections. Darker right face, softly lit upper face. Physically believable substantial depth, crisp thick geometry that survives reduction to Dock size, deliberate smooth corners, no tiny details.
Composition: one straight-on macOS rounded-square graphite ceramic icon tile centered and nearly filling the canvas, with approximately 7% transparent outer safety margin. The cube is centered on the tile, large and visually dominant, occupying about 67% of canvas width and 73% of canvas height. Tiny contact shadow to lift it from the surface. Minimal rich graphite tile surface, restrained gradient and subtle polished rim, not a scene. Orthographic isometric cube, not tilted tile. NO platform under the cube.
Lighting: broad soft studio key from upper left and a very restrained aqua rim, satisfying depth without dazzling flare.
Palette: graphite #111C20, deep petroleum #063B40, turquoise #39D7CC, mint #AEFFF0, cool silver. No copper, gold, purple or rainbow.
Background: genuine alpha transparency OUTSIDE the rounded-square tile and its delicate natural shadow; do not draw a checkerboard, white or black square behind the tile.
Text: absolutely no letters, no words, no PM, no VIREN, no CORP, no caption or watermark.
Constraints: one finished app icon only, no collage, no variants, no interface mockup, no decorations, no sparks, no circuitry network, no hairline detail. High-quality modern 3D product-render finish and exceptionally clean readable silhouette.
```

## Transparency Refinement Prompt

This second built-in-tool pass preserved the design but still returned an opaque PNG, so alpha was prepared locally as described above.

```text
Edit the attached finished app icon. Preserve the cube, all three glyphs, the silver and teal materials, the graphite rounded-square tile, its size and exact composition. Change ONLY the outside background.
The previous output has an actual opaque white/gray checkerboard baked into it. REMOVE that checkerboard completely. Deliver a real PNG cutout with an ALPHA CHANNEL: every pixel outside the rounded-square tile and its subtle soft shadow must be transparent alpha=0, not a visible checkerboard pattern, not white, not gray, not black. Keep antialiased partially transparent edge pixels and the soft shadow. Do not redraw, recolor, crop or change the icon artwork. One square transparent-background PNG app icon. No text or watermark. It must be genuine transparency, suitable for installation as a macOS .icns resource, not a picture of a transparent background.
```
