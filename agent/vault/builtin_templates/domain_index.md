# {{ domain | title }}

> _Add a one-sentence description of this domain's scope._

## Subdomains

_Populated manually or by agent when first subdomain note is written._

## Recent notes

```bases
filter: domain_path starts-with "{{ domain }}"
sort: date_modified desc
limit: 10
show: title, date_modified, content_age, status
```

## High-importance

```bases
filter: domain_path starts-with "{{ domain }}" AND importance = "high"
sort: date_modified desc
show: title, review_after, staleness_risk
```

## Staleness watch

```bases
filter: domain_path starts-with "{{ domain }}" AND review_after < today
sort: review_after asc
show: title, review_after, content_age, staleness_risk
```

## Has verbatim content

```bases
filter: domain_path starts-with "{{ domain }}" AND verbatim_count > 0
show: title, verbatim_types, date_modified
```
