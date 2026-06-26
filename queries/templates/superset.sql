SELECT
  id,
  timestamp,
  uuid,
  country_code,
  school_id,
  giga_id_school,
  results::text AS results_json
FROM measurements
WHERE country_code IN ('MD', 'MW')
  AND DATE(timestamp) >= '@DATE_START@'
  AND DATE(timestamp) < '@DATE_END@'
