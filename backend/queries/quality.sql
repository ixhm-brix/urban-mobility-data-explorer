SELECT rule_code, action, description, record_count
FROM data_quality_rules
ORDER BY CASE action WHEN 'excluded' THEN 1 WHEN 'flagged' THEN 2 ELSE 3 END, record_count DESC;
