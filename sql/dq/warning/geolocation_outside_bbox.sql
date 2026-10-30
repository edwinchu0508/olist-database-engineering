-- Geolocation records (file rows; repeated copies count separately) whose coordinates lie outside the
-- bounding box lat -34..5.3, lng -74..-28.8, which encloses Brazil including its Atlantic islands. The
-- box is a plausibility filter only: it says nothing about where an outside point actually is. These
-- records are excluded from core.zip_prefix_geo.
SELECT geolocation_zip_code_prefix, geolocation_lat, geolocation_lng, geolocation_city, geolocation_state
FROM raw.geolocation
WHERE NOT (geolocation_lat::double precision BETWEEN -34 AND 5.3
       AND geolocation_lng::double precision BETWEEN -74 AND -28.8)
