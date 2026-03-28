# {{ subdomain | title }}

> Subnode of [[{{ domain }}/_index|{{ domain | title }}]].

## All notes

```bases
filter: domain_path = "{{ domain_path }}"
sort: date_modified desc
show: title, source_type, date_created, content_age, staleness_risk, verbatim_count
```

## Staleness watch

```bases
filter: domain_path = "{{ domain_path }}" AND review_after < today
sort: review_after asc
show: title, review_after, staleness_risk
```
