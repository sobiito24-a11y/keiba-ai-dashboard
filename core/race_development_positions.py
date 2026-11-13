"""Display-only netkeiba-style staged race formation from saved pre-race ranks.

No new forecast, horse length/inside-outside inference, scoring changes,
past results, or random positioning. "3 corner" is labelled interpolation.
"""
from collections.abc import Mapping
from math import floor, isfinite

STAGES = ("start", "third", "fourth")
_WEIGHTS = (.34, .23, .17, .12, .09, .05)
_BAND_Y = (5.0, 22.0, 39.0, 56.0, 70.0, 83.0)


def _positive_integer(value, *, maximum):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    if not isfinite(number) or not number.is_integer() or not 1 <= number <= maximum:
        return None
    return int(number)


def _bands(n):
    if n < 1:
        return [0] * len(_WEIGHTS)
    sizes = [floor(n * x) for x in _WEIGHTS]
    extras = n - sum(sizes)
    priorities = sorted(range(len(_WEIGHTS)), key=lambda i: (-(n * _WEIGHTS[i] - sizes[i]), i))
    for i in priorities[:extras]:
        sizes[i] += 1
    return sizes


def _horizontal(count, index, horse_number, band):
    # Tapered horse packs, like the supplied screenshot: wide leading line,
    # progressively narrower groups behind. Horizontal offsets show only
    # separation and NEVER the horse's actual inside/outside track position.
    spacing = 84.0 / max(6, count)
    x = 50.0 + (index - (count - 1) / 2) * spacing
    small_shift = ((horse_number * 7 + band * 3) % 5 - 2) * .65
    return min(93.0, max(7.0, x + small_shift))


def layout(view, *, course_turn="right"):
    """Return three stage lists of deterministic marker coordinates.

    Missing/out-of-range estimates are never invented. For third corner both
    saved estimates MUST exist; continuous interpolation is sorted and only
    then given a tentative displayed ordinal.

    Within each pack, the best estimated position is placed in the facing
    direction: rightmost for a left-turn course (horses face right),
    leftmost for a right-turn course (horses face left). Vertical band and
    saved ranking are NOT inverted. Unknown course direction retains the
    historical layout rather than making up a course turn.
    """
    horses = [h for h in (view or ()) if isinstance(h, Mapping)]
    count = len(horses)
    prepared = []
    for horse in horses:
        no = _positive_integer(horse.get("no"), maximum=99)
        if no is None:
            continue
        start = _positive_integer(horse.get("start_rank"), maximum=count)
        corner = _positive_integer(horse.get("corner"), maximum=count)
        frame = _positive_integer(horse.get("frame"), maximum=8)
        prepared.append(dict(no=no, name=str(horse.get("name") or "馬名未取得"),
                             frame=frame, start=start, fourth=corner,
                             third=(.45 * start + .55 * corner)
                             if start is not None and corner is not None else None))
    output = {}
    for stage in STAGES:
        available = [dict(h) for h in prepared if h[stage] is not None]
        available.sort(key=lambda h: (h[stage], h["frame"] or 99, h["no"]))
        sizes = _bands(len(available))
        index = 0
        for band, size in enumerate(sizes):
            for within in range(size):
                runner = available[index]
                x = _horizontal(size, within, runner["no"], band)
                # With right-facing horse silhouettes (left-turn and straight
                # courses), the leading horse of a horizontal pack belongs
                # on the RIGHT. Clockwise courses retain their left-first row.
                # Only presentation x changes; no saved ranking is reversed.
                if course_turn in ("left", "straight"):
                    x = 100.0 - x
                runner["x"] = round(x, 2)
                runner["y"] = round(_BAND_Y[band] + ((runner["no"] * 3 + band) % 3 - 1) * .45, 2)
                runner["rank_display"] = (
                    index + 1 if stage == "third" else int(runner[stage]))
                runner["band"] = band
                index += 1
        output[stage] = dict(runners=available,
                             missing=[h for h in prepared if h[stage] is None],
                             interpolation=stage == "third")
    return output
