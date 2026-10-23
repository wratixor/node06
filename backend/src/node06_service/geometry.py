"""Deterministic opposite-pair geometry; no extra influence, no recursive layout."""

from .influence import SCALE, InfluenceUnavailable

MODEL = "opposite-pairs-v1-q12"
DEFAULT = [128] * 6


def normalized(values):
    if len(values) != 6 or any(type(x) is not int or not 1 <= x <= 65535 for x in values):
        raise InfluenceUnavailable("INVALID_USER_COORDINATES")
    total = sum(values)
    whole = [v * SCALE // total for v in values]
    order = sorted(range(6), key=lambda j: (-(values[j] * SCALE % total), j))
    for j in order[: SCALE - sum(whole)]:
        whole[j] += 1
    return whole


def color(values):
    # Existing relativeAxis maps components 0/2/4 to +x/+y/+z: red/green/blue.
    channels = [
        (255 * values[j] + (values[j] + values[j + 1]) // 2) // (values[j] + values[j + 1])
        for j in (0, 2, 4)
    ]
    return "#" + "".join(f"{v:02x}" for v in channels)


def calculate(profiles, supports, blocks):
    vectors = {actor: normalized(value) for actor, value in profiles.items()}
    numerator, totals = {}, {}
    for allocations, mirror in ((supports, False), (blocks, True)):
        for actor, row in sorted(allocations.items()):
            vector = vectors.get(actor) or normalized(DEFAULT)
            if mirror:
                vector = [vector[j ^ 1] for j in range(6)]
            for pid, units in sorted(row.items()):
                if units <= 0:
                    continue
                target = numerator.setdefault(pid, [0] * 6)
                totals[pid] = totals.get(pid, 0) + units
                for j in range(6):
                    target[j] += units * vector[j]
    result = {}
    for pid, sums in sorted(numerator.items()):
        total = totals[pid]
        coords = [value // total for value in sums]
        order = sorted(range(6), key=lambda j: (-(sums[j] % total), j))
        for j in order[: SCALE - sum(coords)]:
            coords[j] += 1
        if min(coords) <= 0 or sum(coords) != SCALE:
            raise InfluenceUnavailable("GEOMETRY_NORMALIZATION_FAILED")
        result[pid] = {
            "coordinates": [v / SCALE for v in coords],
            "color": color(coords),
            "model": MODEL,
        }
    return result
