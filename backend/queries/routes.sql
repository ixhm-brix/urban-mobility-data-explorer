-- All origin->destination pairs with enough trips to be meaningful.
-- Deliberately unordered: ranking is done by algorithms/top_k_heap.py.
SELECT o.pu_location_id AS pu_id,
       o.do_location_id AS do_id,
       {od_metrics}
FROM agg_od o
{where}
GROUP BY o.pu_location_id, o.do_location_id
HAVING SUM(trips) >= ?;
