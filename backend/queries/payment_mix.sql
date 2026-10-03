SELECT p.payment_type_id AS id, p.description AS label, s.*
FROM (
    SELECT a.payment_type_id AS pid, {metrics}
    FROM agg_zone_hour a
    {where}
    GROUP BY a.payment_type_id
) s
JOIN payment_types p ON p.payment_type_id = s.pid
ORDER BY s.trips DESC;
