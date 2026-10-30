-- Zip prefixes whose every geolocation record lies outside the bounding box of geolocation_outside_bbox
-- (one row per prefix). They are absent from core.zip_prefix_geo.
SELECT geolocation_zip_code_prefix, count(*) AS points
FROM raw.geolocation
GROUP BY geolocation_zip_code_prefix
HAVING bool_and(NOT (geolocation_lat::double precision BETWEEN -34 AND 5.3
                 AND geolocation_lng::double precision BETWEEN -74 AND -28.8))
