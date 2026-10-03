-- Borough-to-borough trip matrix.
SELECT bp.name AS origin,
       bd.name AS destination,
       {od_metrics}
FROM agg_od o
JOIN zones zp    ON zp.location_id = o.pu_location_id
JOIN zones zd    ON zd.location_id = o.do_location_id
JOIN boroughs bp ON bp.borough_id  = zp.borough_id
JOIN boroughs bd ON bd.borough_id  = zd.borough_id
{where}
GROUP BY bp.name, bd.name;
