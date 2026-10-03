-- One row per calendar day: the month's rhythm (weekends, holidays, weather).
SELECT pickup_date AS date,
       pickup_dow  AS dow,
       {metrics}
FROM agg_zone_hour
{where}
GROUP BY pickup_date
ORDER BY pickup_date;
