# Native Dock icon — 0.56.1

Created with the built-in imagegen tool by editing the previous Native icon.
No CLI or API fallback was used. The existing cube, cyan glyphs and graphite tile remain the design reference.

## Design edit prompt

Use case: style-transfer. Asset type: final macOS Dock application icon, 1024 by 1024 PNG with real alpha transparency outside the rounded-square tile.
Input image 1 is the EDIT TARGET: the current Proto-Mind icon. Improve its readability at 32–64 pixels while preserving its identity: a three-face isometric cube, silver frame, dark faces, cyan geometric glyphs, on a charcoal rounded-square tile.
Keep the cube orientation and the original glyph language: one simple cyan elbow on the top face, a cyan elbow and separate round dot on the left face, a mirrored cyan elbow on the right face. No letters, words, extra symbols, or added objects.
Make a polished but much clearer second version. Enlarge the cube modestly, with a strong single clean silver outline and well-separated dark faces. Make cyan glyph strokes bolder and flatter with crisp edges; keep the dot distinctly separated. Simplify bevels and reduce metallic shine to one restrained highlight. Remove hairline insets, duplicate outlines, rough material texture, etched face borders and glowing bloom. Use smooth graphite and deep teal surfaces with subtle dimensional shading, not photorealistic brushed metal. The small-size silhouette and separation of the three faces are the priorities.
The tile should occupy approximately x=64..960 and y=64..960, with generous rounded corners and a restrained edge. Center the cube with balanced margins. Preserve a fully opaque tile and cube, but fully transparent outer corners and padding. No checkerboard pattern or baked background. Deliver the single standalone finished icon, no presentation sheet, no text or watermark.

## Alpha extraction prompt

The first edit returned an opaque checkerboard outside the tile. A second built-in imagegen edit used this prompt:

Use case: background-extraction. Edit target: the supplied finished Proto-Mind icon. Change ONLY the background outside the rounded-square graphite tile. The gray-and-white checkerboard in this file is incorrectly baked into opaque RGB pixels. Remove that checkerboard completely and output ACTUAL TRANSPARENCY as an alpha channel, alpha=0 in all four outer corners and exterior padding. Preserve the tile, cube, glyphs, colors, geometry, placement and lighting exactly. Do not draw another checkerboard, white background, or black background. This is an exported app asset, not a depiction of transparency. Deliver a 1024x1024 RGBA PNG with smooth antialiased transparent outer edges and the center fully opaque.

## Export

The alpha-corrected result was resampled from 1254 × 1254 to the standard 1024 × 1024 PNG master with macOS `sips`. `scripts/build_native_icon.sh` produces the standard ICNS sizes from `assets/proto_mind_native_icon.png`.

