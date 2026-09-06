# deltaskin-animator

Adds pressed-button animations to [Delta](https://github.com/rileytestut/Delta)
controller skins that don't have them.

Delta 2.0 supports *animated* controller skins
([commit 3e651d9](https://github.com/rileytestut/Delta/commit/3e651d9), July 2026): a
button you're holding sinks into the screen, and a d-pad tilts towards the direction
you're pressing. It's a small thing that makes a skin feel a lot less like a picture
of a controller. But a skin only gets it if the artist built it in, and most skins
predate the feature.

This tool retrofits it. Point it at a `.deltaskin` and it works out where each
button's artwork is, cuts it out, and writes a new skin with the animation wired up.
Your original file is not touched.

```
python3 animate.py "My Skin.deltaskin"
```

The rebuilt skin keeps the original's name and identifier, so importing it into Delta
**replaces** the skin you already have rather than adding a second copy with the same
name. At rest it is pixel-for-pixel identical to the skin you started with.

## Requirements

Python 3.8+ and [Pillow](https://pillow.readthedocs.io/). No other dependencies.

```
pip install -r requirements.txt
```

## Usage

Animate one skin, or a whole folder of them:

```
python3 animate.py "My Skin.deltaskin"
python3 animate.py ~/Downloads/skins -o animated
```

Rebuilt skins land in `./animated` by default (`-o` to change it). Each one prints
what it found:

```
  iphone/edgeToEdge/portrait  1290x2796
     + a       frame 172x172  art 166x167  asset 274x278  moves 1.40pt (70%)  [detected, band 5.50pt, damped 20%]
     + dpad    frame 380x380  art 374x374  asset 462x462  moves 2.43pt (81%)  [detected, band 4.50pt]
     - touchscreen        touchScreen
     - fastForward        too large
```

`moves` is how far the artwork's edge actually travels when pressed, and what
fraction that is of what a hand-built animated skin gets. `-q` prints only the
totals.

Then check the result:

```
python3 verify.py animated/"My Skin.deltaskin"
```

This composites every overlay at rest and confirms it reproduces the base image
exactly — which catches any error in the crop, the declared asset size, or the
centring. Add `--original` to also confirm the name, identifier and touch targets
came through unchanged:

```
python3 verify.py animated/"My Skin.deltaskin" --original "My Skin.deltaskin"
```

To see what a press will look like without installing anything, `--render` writes
before/after close-ups (`renders/` by default):

```
python3 verify.py animated/"My Skin.deltaskin" --render          # every button
python3 verify.py animated/"My Skin.deltaskin" --render dpad a   # just these
python3 verify.py animated/"My Skin.deltaskin" --overview        # whole view
```

`press.py` reproduces DeltaCore's transform exactly, so these renders are what the
device will do, not an approximation.

## Which buttons get animated

Every button with artwork the tool can find. Some items are skipped because there is
nothing there to animate:

- **Touchscreens and thumbsticks** — Delta animates thumbsticks itself.
- **Combo zones** — the diagonal region where two d-pad inputs overlap has no
  artwork of its own.
- **Full-screen gesture areas** — an invisible `fastForward` covering a third of the
  view isn't a button.
- **Items sitting on an emulator screen.**
- **Items sharing artwork.** If two items resolve to the same art, only one can
  animate it. A d-pad wins, since its tilt is the whole point; otherwise the item
  whose frame sits inside the other's gives way.

If a button's artwork can't be made out at all, the tool animates the shape of its
touch frame instead — a circle if the frame is square, a capsule if it's long — so
the button still responds. That's the fallback, not the normal path, and it shows up
as `frame shape` in the output.

## How it works

The hard part isn't the animation, it's that **the base image still has the button
painted into it.**

Hand-built animated skins cut each button out of the layered source art, so the base
image has a hole where the button was and the separate button image fills it. We only
have the flattened PNG. We can't punch a hole in it, because Delta's skin picker
renders the base image on its own — a hole would show up in the thumbnail.

So each overlay is cut from the flattened image and left sitting exactly where it came
from. At rest it's an identical copy of what's underneath, so it's invisible. When
pressed it shrinks — and uncovers the original button's edge, still painted in the
base image underneath. A ghost outline.

The fix is to carry a band of surrounding background along with the button, wide
enough to cover the edge it moved away from. That band is the whole difficulty:

- **Too narrow** and the old edge shows through.
- **Too wide** and it drags neighbouring artwork along — the dish ring around a
  d-pad warping with the press, the bezel beyond a button's plate clipping over it.
- **Also too wide** and the animation gets weaker, not just uglier. Delta centres the
  overlay on the item's frame and scales it about that centre, so a larger overlay
  means the artwork inside it moves proportionally less. Every pixel of band costs
  responsiveness.

So the band is grown outward from the artwork through smooth background only, stopping
dead at any edge that isn't the button's own (a geodesic dilation — it can't step over
a fence). Then the width is *measured* rather than guessed: each candidate overlay is
run through the real transform in all nine press states, and the narrowest band whose
pressed footprint still covers the artwork's resting footprint wins. Coverage is
judged on both leaked area and gap thickness, because a hairline where a button
touches something else is invisible while a thin ring all the way around is exactly
the ghost we're avoiding.

Where a button is fenced in so tightly that even the widest band can't cover it, the
asset box is padded symmetrically instead. That damps the movement — less travel, but
no ghost. Buttons tangent to the edge of the plate they sit on usually end up here.

`skinlib.py` finds the artwork, `press.py` is DeltaCore's transform, `animate.py`
chooses each band and writes the skins, `verify.py` checks them.

## Limitations

- Tuned for skins drawn as **flat or softly shaded shapes with a defined rim** — the
  neumorphic and photorealistic styles most Delta skins use. Heavily textured
  backgrounds (carbon weave, camo) read as edges and can fence a band in early,
  which shows up as damping.
- A skin whose representations point at **different base images per orientation** has
  its overlays cut from the first one. Check the output for a `!` warning.
- Only the flattened image is available, so a button that visually overlaps another
  can't be fully separated from it.
- Nothing here needs a device, but nothing here has been tested on every skin in the
  wild either. Run `verify.py` and look at a couple of `--render` close-ups before
  trusting a rebuild.

## Credits

Delta and DeltaCore are by [Riley Testut](https://github.com/rileytestut); animated
controller skin support is his, and this tool just fills in the per-button assets his
format expects. The skins you point it at belong to whoever drew them — this
repository ships no skin artwork, and please don't redistribute a rebuilt skin without
the artist's blessing.

## License

MIT — see [LICENSE](LICENSE).
