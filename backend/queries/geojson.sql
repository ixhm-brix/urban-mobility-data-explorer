SELECT g.location_id, z.zone_name AS zone, b.name AS borough, s.name AS service_zone, g.geojson
FROM zone_geometry g
JOIN zones z         ON z.location_id     = g.location_id
JOIN boroughs b      ON b.borough_id      = z.borough_id
JOIN service_zones s ON s.service_zone_id = z.service_zone_id;
