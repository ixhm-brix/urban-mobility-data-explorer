-- Day-of-week x hour grid. January 2019 has five Tue/Wed/Thu and four of every
-- other weekday, so counts are divided by the number of matching dates.
SELECT pickup_dow  AS dow,
       pickup_hour AS hour,
       COUNT(DISTINCT pickup_date) AS days,
       ROUND(1.0 * SUM(trips) / COUNT(DISTINCT pickup_date), 1) AS trips_per_day,
       {metrics}
FROM agg_zone_hour
{where}
GROUP BY pickup_dow, pickup_hour;
