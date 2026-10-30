-- New version of core.zip_prefix_geo: one row per zip prefix.
--
-- Unit of aggregation: a distinct geolocation *record*, i.e. a distinct (prefix, lat, lng, city,
-- state) combination. Exact duplicate rows count once, however often they repeat; the same
-- coordinates recorded under two city spellings count twice. Both the median coordinates and the
-- most frequent city/state are computed over these records, not over raw rows.
--
-- Coordinates are compared as numbers, so "-23.5" and "-23.50" are the same record.
--
-- Records outside the bounding box lat -34..5.3, lng -74..-28.8 are left out (DQ warning
-- geolocation_outside_bbox). The box encloses Brazil including its Atlantic islands: Fernando de
-- Noronha, prefix 53990, lies at longitude -32.4. A prefix with no record inside the box gets no row.
-- mode() resolves ties by taking the first value in sort order, so the result is deterministic.
SELECT zip_code_prefix,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY lat) AS lat,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY lng) AS lng,
       mode() WITHIN GROUP (ORDER BY city)             AS city,
       mode() WITHIN GROUP (ORDER BY state)            AS state,
       count(*)::integer                                AS source_points
FROM (
    SELECT DISTINCT geolocation_zip_code_prefix        AS zip_code_prefix,
                    geolocation_lat::double precision  AS lat,
                    geolocation_lng::double precision  AS lng,
                    geolocation_city                   AS city,
                    geolocation_state                  AS state
    FROM raw.geolocation
) AS records
WHERE lat BETWEEN -34 AND 5.3
  AND lng BETWEEN -74 AND -28.8
GROUP BY zip_code_prefix
