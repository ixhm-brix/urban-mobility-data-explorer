-- Headline KPIs for the current filter set.
SELECT {metrics},
       COUNT(DISTINCT pickup_date) AS days
FROM agg_zone_hour
{where};
