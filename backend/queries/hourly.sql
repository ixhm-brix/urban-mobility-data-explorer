-- Hour-of-day profile. `days` lets the client show an average day, not a sum.
SELECT s.*, tb.band AS time_band
FROM (
    SELECT a.pickup_hour AS hour,
           COUNT(DISTINCT a.pickup_date) AS days,
           {metrics}
    FROM agg_zone_hour a
    {where}
    GROUP BY a.pickup_hour
) s
JOIN time_bands tb ON tb.hour = s.hour
ORDER BY s.hour;
