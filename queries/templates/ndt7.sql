SELECT TO_JSON_STRING(t) AS row
FROM `measurement-lab.ndt.ndt7` AS t
WHERE date >= '@DATE_START@' AND date < '@DATE_END@'
  AND (
    client.Geo.CountryCode = 'MW'
    OR client.Geo.CountryCode = 'MD'
  )
  AND (
    (SELECT cm.Value
     FROM UNNEST(raw.Download.ClientMetadata) AS cm
     WHERE cm.Name = 'client_name') = 'giga-meter'
    OR
    (SELECT cm.Value
     FROM UNNEST(raw.Upload.ClientMetadata) AS cm
     WHERE cm.Name = 'client_name') = 'giga-meter'
  )
