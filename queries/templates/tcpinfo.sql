SELECT TO_JSON_STRING(t) AS row
FROM `measurement-lab.ndt.tcpinfo` AS t
WHERE date >= '@DATE_START@' AND date < '@DATE_END@'
  AND id IN (
    SELECT id
    FROM `measurement-lab.ndt.ndt7`
    WHERE date >= '@DATE_START@' AND date < '@DATE_END@'
      AND client.Geo.CountryCode IN ('MW', 'MD')
      AND (
        (SELECT cm.Value
         FROM UNNEST(raw.Download.ClientMetadata) AS cm
         WHERE cm.Name = 'client_name') = 'giga-meter'
        OR
        (SELECT cm.Value
         FROM UNNEST(raw.Upload.ClientMetadata) AS cm
         WHERE cm.Name = 'client_name') = 'giga-meter'
      )
  )
