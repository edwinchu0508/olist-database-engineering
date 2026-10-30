-- Redundant copies of identical geolocation rows (the first copy of each is not counted).
SELECT geolocation_zip_code_prefix, geolocation_lat, geolocation_lng, geolocation_city, geolocation_state, copy_no
FROM (
    SELECT g.*,
           row_number() OVER (PARTITION BY geolocation_zip_code_prefix, geolocation_lat, geolocation_lng,
                                           geolocation_city, geolocation_state) AS copy_no
    FROM raw.geolocation AS g
) AS numbered
WHERE copy_no > 1
