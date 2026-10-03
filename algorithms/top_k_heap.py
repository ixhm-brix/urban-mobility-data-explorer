"""
Top-K selection with a hand-written binary min-heap — no heapq, no sorted(),
no list.sort(), no max()/min().

Problem
-------
The dashboard ranks things constantly: the busiest routes out of ~32 000
origin→destination pairs, the slowest zones out of 263, the most circuitous
routes. The SQL returns *unordered* aggregates and this module picks the K best.

Why a heap
----------
Sorting all n candidates costs O(n log n) and holds every one in order. We only
need K (10–25) of them, so we keep a min-heap of size K whose root is the
*weakest* of the current best K:

    for each candidate:
        if heap has < K items:           push            O(log K)
        elif candidate beats the root:   replace root    O(log K)
        else:                            discard         O(1)

Total O(n log K) time and O(K) extra memory. For n = 32 000 and K = 10 that is
~32 000 × 3.3 ≈ 106 k comparisons instead of ~32 000 × 15 ≈ 480 k for a sort.
The final K items are ordered with a hand-written merge sort, O(K log K).

Pseudo-code
-----------
    TOP_K(items, K, score):
        H ← empty array
        for x in items:
            s ← score(x)
            if |H| < K:   H.append((s, x)); SIFT_UP(H, |H|-1)
            elif s > H[0].s:  H[0] ← (s, x); SIFT_DOWN(H, 0)
        return MERGE_SORT_DESC(H)

    SIFT_UP(H, i):   while i > 0 and H[i].s < H[parent(i)].s: swap; i ← parent(i)
    SIFT_DOWN(H, i): while a child is smaller, swap with the smaller child

Ties are broken by insertion order (earlier wins) so results are deterministic.
"""
from __future__ import annotations

from typing import Any, Callable, Iterable


class MinHeap:
    """Array-backed binary min-heap of (score, seq, item) entries."""

    def __init__(self) -> None:
        self._a: list = []

    def __len__(self) -> int:
        return len(self._a)

    def peek(self):
        return self._a[0]

    @staticmethod
    def _less(x, y) -> bool:
        # Lower score is "less". On equal scores the *later* item is less, so it is
        # the first to be evicted — earlier items win ties.
        if x[0] != y[0]:
            return x[0] < y[0]
        return x[1] > y[1]

    def push(self, entry) -> None:
        a = self._a
        a.append(entry)
        i = len(a) - 1
        while i > 0:
            parent = (i - 1) // 2
            if self._less(a[i], a[parent]):
                a[i], a[parent] = a[parent], a[i]
                i = parent
            else:
                break

    def replace_root(self, entry) -> None:
        a = self._a
        a[0] = entry
        n, i = len(a), 0
        while True:
            left, right, smallest = 2 * i + 1, 2 * i + 2, i
            if left < n and self._less(a[left], a[smallest]):
                smallest = left
            if right < n and self._less(a[right], a[smallest]):
                smallest = right
            if smallest == i:
                return
            a[i], a[smallest] = a[smallest], a[i]
            i = smallest

    def entries(self) -> list:
        return list(self._a)


def merge_sort_desc(entries: list) -> list:
    """Stable merge sort, highest score first (ties keep insertion order)."""
    n = len(entries)
    if n <= 1:
        return entries
    mid = n // 2
    left, right = merge_sort_desc(entries[:mid]), merge_sort_desc(entries[mid:])
    out, i, j = [], 0, 0
    while i < len(left) and j < len(right):
        l, r = left[i], right[j]
        # take left when it scores higher, or ties and was seen earlier
        if l[0] > r[0] or (l[0] == r[0] and l[1] < r[1]):
            out.append(l); i += 1
        else:
            out.append(r); j += 1
    while i < len(left):
        out.append(left[i]); i += 1
    while j < len(right):
        out.append(right[j]); j += 1
    return out


def top_k(items: Iterable[Any], k: int, score: Callable[[Any], float | None],
          largest: bool = True) -> list:
    """Return the k items with the highest (or lowest) score, best first.
    Items whose score is None are skipped."""
    if k <= 0:
        return []
    heap = MinHeap()
    sign = 1 if largest else -1
    seq = 0
    for item in items:
        s = score(item)
        if s is None:
            continue
        entry = (sign * s, seq, item)
        seq += 1
        if len(heap) < k:
            heap.push(entry)
        elif MinHeap._less(heap.peek(), entry):
            heap.replace_root(entry)
    return [e[2] for e in merge_sort_desc(heap.entries())]


if __name__ == "__main__":
    import random
    rng = random.Random(7)
    data = [{"id": i, "v": rng.random()} for i in range(10_000)]
    got = [d["id"] for d in top_k(data, 10, lambda d: d["v"])]
    want = [d["id"] for d in sorted(data, key=lambda d: -d["v"])[:10]]  # reference check only
    assert got == want, (got, want)
    low = [d["id"] for d in top_k(data, 5, lambda d: d["v"], largest=False)]
    assert low == [d["id"] for d in sorted(data, key=lambda d: d["v"])[:5]]
    ties = top_k([("a", 1), ("b", 2), ("c", 2), ("d", 1)], 2, lambda t: t[1])
    assert ties == [("b", 2), ("c", 2)], ties
    print("top_k self-test passed")
