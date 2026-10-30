-- Zip prefixes recorded under more than one city spelling (accents, case, abbreviations; one row per
-- prefix). core.zip_prefix_geo keeps the most frequent spelling.
SELECT geolocation_zip_code_prefix, count(DISTINCT geolocation_city) AS spellings
FROM raw.geolocation
GROUP BY geolocation_zip_code_prefix
HAVING count(DISTINCT geolocation_city) > 1
