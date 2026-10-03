-- One page of the trip explorer. {order} is chosen from a whitelist in routes/trips.py.
-- The inner query picks the page from `trips` alone (walking an ORDER BY index where it
-- can); only those 25 rows are then joined to their labels.
SELECT t.trip_id, t.pickup_datetime, t.dropoff_datetime,
       t.pu_location_id, zp.zone_name AS pu_zone, bp.name AS pu_borough,
       t.do_location_id, zd.zone_name AS do_zone, bd.name AS do_borough,
       t.passenger_count, t.trip_distance, t.trip_duration_min, t.avg_speed_mph,
       t.fare_amount, t.tip_amount, t.tip_pct, t.total_amount, t.fare_per_mile,
       p.description AS payment
FROM (
    SELECT * FROM trips t
    {where}
    ORDER BY {order}
    LIMIT ? OFFSET ?
) t
JOIN zones zp         ON zp.location_id    = t.pu_location_id
JOIN zones zd         ON zd.location_id    = t.do_location_id
JOIN boroughs bp      ON bp.borough_id     = zp.borough_id
JOIN boroughs bd      ON bd.borough_id     = zd.borough_id
JOIN payment_types p  ON p.payment_type_id = t.payment_type_id
ORDER BY {order};
