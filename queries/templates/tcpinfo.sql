-- We extend the query range of the outer query by one
-- day in the past and in the future, while keeping the
-- inner query strictly limited to the window. There
-- are two reasons for doing this:
--
-- (a) extend the outer query to account for potential
-- cases in which the tcp-info row was attributed to the
-- previous or next day (when the specific test fell on
-- a boundary between a day and the next day)
--
-- (b) avoid doing the same for the inner query to avoid
-- pulling the same UUID twice for adjacent chunks
--
-- This case is obviously a corner case, but it makes
-- sense to write a more robust query anyway.
SELECT TO_JSON_STRING(t) AS row
FROM `measurement-lab.ndt.tcpinfo` AS t
WHERE date >= DATE_SUB(DATE '@DATE_START@', INTERVAL 1 DAY)
  AND date < DATE_ADD(DATE '@DATE_END@', INTERVAL 1 DAY)
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
