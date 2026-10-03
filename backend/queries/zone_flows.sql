-- Where trips starting in a zone go ({side}=pu) or where trips ending in it came from ({side}=do).
SELECT o.{other}_location_id AS location_id,
       z.zone_name AS zone, b.name AS borough,
       {od_metrics}
FROM agg_od o
JOIN zones z    ON z.location_id = o.{other}_location_id
JOIN boroughs b ON b.borough_id  = z.borough_id
WHERE o.{side}_location_id = ? {extra}
GROUP BY o.{other}_location_id;
