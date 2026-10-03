-- Per pickup-zone measures for the choropleth and zone rankings.
SELECT s.*, z.zone_name AS zone, b.name AS borough
FROM (
    SELECT a.pu_location_id AS location_id, {metrics}
    FROM agg_zone_hour a
    {where}
    GROUP BY a.pu_location_id
) s
JOIN zones z    ON z.location_id = s.location_id
JOIN boroughs b ON b.borough_id  = z.borough_id;
