# Native Dock icon — 0.71.1

Created on 2026-09-22 with the built-in ImageGen tool. The operator explicitly
approved a complete redraw that retains the cube idea. No CLI or API fallback
was used.

The new mark is a single softly bevelled glass cube on a graphite tile, with
broad aqua/teal faces and a restrained central highlight. The old glyphs and
heavy silver frame were removed to improve the small-size silhouette.

## Final generation prompt

Use case: logo-brand.
Asset type: final production macOS application icon for Proto-Mind. One single standalone square 1024x1024 RGBA icon, with actual alpha transparency outside its rounded-square tile.

Create a completely new, elegant, memorable icon for an AI workspace whose recognizable identity is a cube. Design it as an expensive, carefully art-directed native Mac application icon, not generic AI clipart.

Composition: a single softly bevelled ISOMETRIC CUBE floating just above the center of an opaque graphite squircle tile. Show exactly three solid planar faces: top, left, right. A balanced hexagonal outer silhouette, without a heavy cage, outline, or extra inner boxes. Cube occupies about 64 percent of canvas width and 69 percent height, centered optically. Tile occupies x=64..960 and y=64..960 with generous continuous rounded corners. Plenty of calm space around the cube.

Material and light: a sculptural cube of thick satin optical glass, smooth broad surfaces, subtle internal depth. Top face pale icy aqua lit from upper left; left face rich translucent turquoise; right face deep teal blue with one restrained luminous edge. A small soft cyan-white light lives within the glass near the central three-face junction, giving the cube a sense of a quiet intelligent core. Very restrained bloom that never blurs the silhouette. Rounded bevels with one clean soft specular highlight. Subtle short contact shadow, no exaggerated reflection. Neutral dark charcoal tile with a very understated top-to-bottom tonal gradient; no busy texture. All three faces must remain visually distinct and beautiful when reduced to 32 or 48 pixels. Large broad color fields, precise geometry, polished finish.

The result should feel calm, confident, tactile, futuristic and premium. Simple enough to remember and recognize in one glance. A sophisticated cube sculpture, no decorative tech clutter.
No letters, glyphs, terminal symbols, circuits, dots on faces, robot eyes, metallic frame, neon wireframe, nested cubes, stars, particles, extra objects, multiple variants, text, watermark, mockup or perspective tilt of the tile itself.
Transparency requirement: only the exterior beyond the tile is genuinely transparent alpha=0. All tile and central cube pixels are opaque. No checkerboard drawn into pixels, no white or black canvas background around the tile. Output the finished icon asset only.

## Alpha cleanup prompts

Two built-in ImageGen cleanup edits removed residual near-transparent corner
pixels. The final export passes the existing exact-zero corner checks without
changing their tolerance.

First cleanup:

Use case: background-extraction.
Edit target: the supplied finished Proto-Mind glass-cube app icon. The user has approved this exact design. Preserve the cube, shape, colors, lighting, glyph-free glass faces, rounded graphite tile, composition, relative dimensions, and all artwork EXACTLY.
Change only the alpha channel / exterior transparency for production export. The current image has residual alpha=1 out of 255 at some far outer-corner pixels. Remove all stray exterior pixels so every corner and all empty padding outside the rounded graphite tile are genuinely alpha=0. The tile and every interior pixel should be fully opaque alpha=255, with antialiasing ONLY along the silhouette of the tile. Keep the glass look as rendered color; do not make the tile or the glass cube alpha-transparent.
Export a clean RGBA PNG, preferably 1024 x 1024. No checkerboard, background color, new image design, extra objects, text, or watermark. This is technical cleanup only of the supplied icon, not a redesign.

Final cleanup:

Use case: background-extraction. The input is the approved finished Proto-Mind app icon; do not redesign it or change its RGB artwork. A production alpha cleanup only: erase every pixel in the outermost 24-pixel border on all four sides of the canvas to exact alpha 0. This border is already outside the icon tile, so no visible artwork is touched. In particular the bottom-left corner must be completely empty transparent, no residual opacity whatsoever. Keep the cube and tile exactly unchanged and fully opaque. Retain the soft antialiased rounded tile boundary. Return one RGBA PNG with actual transparency, no checkerboard, no black or white background, no additional text or objects.

## Export

The generated RGBA image was resampled from 1254 × 1254 to the 1024 × 1024
PNG master with macOS `sips`, preserving alpha. The project asset is
`assets/proto_mind_native_icon.png`; `scripts/build_native_icon.sh` packages
its standard 16–1024-pixel representations into the application's ICNS file.
The previous asset remains available in Git history.
