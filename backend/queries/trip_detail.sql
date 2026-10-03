SELECT t.*,
       v.name  AS vendor, r.description AS rate_code, p.description AS payment,
       zp.zone_name AS pu_zone, bp.name AS pu_borough, zp.centroid_lon AS pu_lon, zp.centroid_lat AS pu_lat,
       zd.zone_name AS do_zone, bd.name AS do_borough, zd.centroid_lon AS do_lon, zd.centroid_lat AS do_lat,
       tb.band AS time_band, db.label AS distance_band, fb.label AS fare_band
FROM trips t
JOIN vendors v         ON v.vendor_id         = t.vendor_id
JOIN rate_codes r      ON r.rate_code_id      = t.rate_code_id
JOIN payment_types p   ON p.payment_type_id   = t.payment_type_id
JOIN zones zp          ON zp.location_id      = t.pu_location_id
JOIN zones zd          ON zd.location_id      = t.do_location_id
JOIN boroughs bp       ON bp.borough_id       = zp.borough_id
JOIN boroughs bd       ON bd.borough_id       = zd.borough_id
JOIN time_bands tb     ON tb.hour             = t.pickup_hour
JOIN distance_bands db ON db.distance_band_id = t.distance_band_id
JOIN fare_bands fb     ON fb.fare_band_id     = t.fare_band_id
WHERE t.trip_id = ?;
