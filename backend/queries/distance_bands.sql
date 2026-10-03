-- Economics by trip length: how price per mile and speed change with distance.
-- Aggregate first, then attach labels: joining the 6-row band table up front makes
-- SQLite rescan the roll-up once per band.
SELECT d.distance_band_id AS band_id, d.label, s.*
FROM (
    SELECT a.distance_band_id AS bid, {metrics}
    FROM agg_zone_hour a
    {where}
    GROUP BY a.distance_band_id
) s
JOIN distance_bands d ON d.distance_band_id = s.bid
ORDER BY d.distance_band_id;
