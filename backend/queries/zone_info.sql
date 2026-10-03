SELECT z.location_id, z.zone_name AS zone, b.name AS borough, s.name AS service_zone,
       z.centroid_lon, z.centroid_lat, z.area_km2
FROM zones z
JOIN boroughs b      ON b.borough_id      = z.borough_id
JOIN service_zones s ON s.service_zone_id = z.service_zone_id
WHERE z.location_id = ?;
