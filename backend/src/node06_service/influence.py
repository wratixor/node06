"""T1 v1: conserved half budgets, deterministic fixed-point decisions, no geometry."""

import math
from decimal import Decimal, localcontext

SCALE = 10**12
MODEL = "t1-v2-d0.5-q12-signed-slots"


class InfluenceUnavailable(RuntimeError):
    pass


def calculate(user_ids, trust, subscriptions):
    ids = sorted(set(user_ids))
    if len(ids) > 10000 or len(trust) > 100000 or len(subscriptions) > 100000:
        raise InfluenceUnavailable("INFLUENCE_CAPACITY_EXCEEDED")
    people = set(ids)
    targets = {uid: {uid} for uid in ids}
    for source, target in trust:
        if source in people and target in people:
            targets[source].add(target)
    weights = dict.fromkeys(ids, 1.0)
    for _ in range(128):
        new = dict.fromkeys(ids, 0.5)
        for source in ids:
            share = 0.5 * weights[source] / len(targets[source])
            for target in sorted(targets[source]):
                new[target] += share
        residual = math.fsum(abs(new[uid] - weights[uid]) for uid in ids)
        weights = new
        if residual <= 1e-12 * max(1, len(ids)):
            break
    else:
        raise InfluenceUnavailable("INFLUENCE_DID_NOT_CONVERGE")
    if abs(math.fsum(weights.values()) - len(ids)) > 1e-9 * max(1, len(ids)):
        raise InfluenceUnavailable("INFLUENCE_CONSERVATION_FAILED")
    # Quantize HALF weights by largest remainder; then both budgets are exactly
    # equal and the total remains exactly N, despite floating-point iteration.
    with localcontext() as ctx:
        ctx.prec = 50
        exact = {uid: Decimal(str(weights[uid])) for uid in ids}
        total = sum(exact.values())
        quotas = {uid: exact[uid] * len(ids) * (SCALE // 2) / total for uid in ids}
        half = {uid: int(quotas[uid]) for uid in ids}
        remainder = len(ids) * (SCALE // 2) - sum(half.values())
        if not 0 <= remainder <= len(ids):
            raise InfluenceUnavailable("INFLUENCE_QUANTIZATION_FAILED")
        ranked = sorted(ids, key=lambda uid: (-(quotas[uid] - half[uid]), uid))
        for uid in ranked[:remainder]:
            half[uid] += 1
    by_user = {uid: [] for uid in ids}
    for user, point in subscriptions:
        if user in people:
            by_user[user].append(point)
    allocations = {}
    idle = 0
    for uid in ids:
        points = sorted(set(by_user[uid]))
        if not points:
            idle += half[uid]
            continue
        quotient, extra = divmod(half[uid], len(points))
        allocations[uid] = {pid: quotient + (i < extra) for i, pid in enumerate(points)}
    assert sum(half.values()) == len(ids) * SCALE // 2
    assert sum(sum(row.values()) for row in allocations.values()) + idle == sum(half.values())
    return {
        "model": MODEL,
        "scale": SCALE,
        "active_users": len(ids),
        "people_units": sum(half.values()),
        "idle_units": idle,
        "weights": {uid: 2 * half[uid] for uid in ids},
        "allocations": allocations,
    }


def amount(units):
    whole, fraction = divmod(units, SCALE)
    return f"{whole}.{fraction:012d}".rstrip("0").rstrip(".")
